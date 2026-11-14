"""Silver layer standardization, fingerprint generation, and quality quarantine rules.

Applies deterministic SHA-256 fingerprinting for trip deduplication, standardizes
timestamp semantics to America/New_York local wall-clock time, splits invalid rows
into quarantine, and applies windowed deduplication.
"""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from pyspark.sql.types import TimestampType

from nyc_taxi_data_platform.config import QualityConfig


def trip_fingerprint_expr() -> F.Column:
    """Generate a deterministic SHA-256 hash expression across core trip attributes.

    Uses vendor, timestamps, pickup/dropoff locations, distance, and fare to detect
    exact duplicate trip entries.

    Returns:
        Column expression producing the 64-character hex hash.
    """
    return F.sha2(
        F.concat_ws(
            "|",
            F.col("vendor_id").cast("string"),
            F.col("tpep_pickup_datetime").cast("string"),
            F.col("tpep_dropoff_datetime").cast("string"),
            F.col("pickup_location_id").cast("string"),
            F.col("dropoff_location_id").cast("string"),
            F.col("trip_distance").cast("string"),
            F.col("fare_amount").cast("string"),
        ),
        256,
    )


def standardize_bronze_trips(df: DataFrame, local_timezone: str) -> DataFrame:
    """Project Bronze columns to Silver trip schema with NYC local wall-clock semantics.

    Args:
        df: Input Bronze DataFrame.
        local_timezone: Standard timezone string (e.g. 'America/New_York').

    Returns:
        DataFrame matching Silver trips schema.
    """
    return df.select(
        trip_fingerprint_expr().alias("trip_fingerprint"),
        F.col("source_file"),
        F.col("source_month"),
        F.col("ingestion_run_id"),
        F.col("vendor_id"),
        F.col("tpep_pickup_datetime").cast(TimestampType()).alias("pickup_datetime"),
        F.col("tpep_dropoff_datetime").cast(TimestampType()).alias("dropoff_datetime"),
        F.col("pickup_location_id").alias("pickup_zone_id"),
        F.col("dropoff_location_id").alias("dropoff_zone_id"),
        F.col("trip_distance"),
        F.col("fare_amount"),
        F.col("passenger_count"),
        F.col("payment_type"),
        F.lit(local_timezone).alias("local_timezone"),
        F.current_timestamp().alias("processed_at"),
    )


def validation_flags(quality: QualityConfig) -> F.Column:
    """Boolean column expression flagging records violating quality rules.

    Flags rows with:
        - Missing or negative timestamps
        - Dropoff before pickup
        - Null or non-positive location IDs
        - Negative or excessive trip distance
        - Fare amounts outside acceptable range

    Args:
        quality: QualityConfig instance with threshold limits.

    Returns:
        Boolean Column evaluating to True for invalid rows.
    """
    return (
        F.col("pickup_datetime").isNull()
        | F.col("dropoff_datetime").isNull()
        | (F.col("dropoff_datetime") < F.col("pickup_datetime"))
        | F.col("pickup_zone_id").isNull()
        | F.col("dropoff_zone_id").isNull()
        | (F.col("pickup_zone_id") <= 0)
        | (F.col("dropoff_zone_id") <= 0)
        | F.col("trip_distance").isNull()
        | (F.col("trip_distance") < 0)
        | (F.col("trip_distance") > quality.max_trip_distance_miles)
        | F.col("fare_amount").isNull()
        | (F.col("fare_amount") < quality.min_fare_amount)
        | (F.col("fare_amount") > quality.max_fare_amount)
    )


def split_valid_and_quarantine(
    standardized: DataFrame, quality: QualityConfig
) -> tuple[DataFrame, DataFrame]:
    """Split standardized trips into valid and quarantined DataFrames.

    Args:
        standardized: Standardized Silver trips DataFrame.
        quality: QualityConfig instance containing thresholds.

    Returns:
        Tuple of (valid_trips_df, quarantined_trips_df).
    """
    invalid = standardized.filter(validation_flags(quality))
    valid = standardized.filter(~validation_flags(quality))

    quarantined = invalid.select(
        F.col("source_file"),
        F.col("source_month"),
        F.col("ingestion_run_id"),
        F.lit("validation_failed").alias("rejection_reason"),
        F.to_json(
            F.struct(
                F.col("trip_fingerprint"),
                F.col("pickup_datetime"),
                F.col("dropoff_datetime"),
                F.col("pickup_zone_id"),
                F.col("dropoff_zone_id"),
            )
        ).alias("raw_payload"),
        F.current_timestamp().alias("processed_at"),
    )
    return valid, quarantined


def deduplicate_trips(df: DataFrame) -> DataFrame:
    """Deduplicate trips by keeping the earliest processed row per fingerprint.

    Args:
        df: Input DataFrame containing trip_fingerprint and processed_at columns.

    Returns:
        Deduplicated DataFrame.
    """
    from pyspark.sql.window import Window

    window = Window.partitionBy("trip_fingerprint").orderBy(F.col("processed_at").asc())
    return (
        df.withColumn("_row_num", F.row_number().over(window))
        .filter(F.col("_row_num") == 1)
        .drop("_row_num")
    )
