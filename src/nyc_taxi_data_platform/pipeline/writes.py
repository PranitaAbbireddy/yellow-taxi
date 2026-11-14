"""Delta table write helpers for idempotent loading and merging.

Encapsulates MERGE INTO operations for ingestion manifests and Gold hourly facts,
as well as partition-scoped overwrites for Silver trips and Bronze appends.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from nyc_taxi_data_platform.config import PipelineConfig, load_config


def _fqn(config: PipelineConfig, schema: str, table: str) -> str:
    """Helper to build a three-level table identifier."""
    return config.table_fqn(schema, table)


def merge_manifest(spark: SparkSession, manifest_df: DataFrame) -> None:
    """Merge incoming manifest record into the bronze.ingestion_manifest table.

    Uses WHEN NOT MATCHED THEN INSERT to record new files without duplicating keys.

    Args:
        spark: Active SparkSession.
        manifest_df: Single-row or batch DataFrame of ManifestRecord entries.
    """
    config = load_config()
    table = _fqn(config, config.bronze_schema, "ingestion_manifest")
    manifest_df.createOrReplaceTempView("incoming_manifest")
    spark.sql(
        f"""
        MERGE INTO {table} AS t
        USING incoming_manifest AS s
        ON t.source_file_identity = s.source_file_identity
        WHEN NOT MATCHED THEN INSERT *
        """
    )


def append_bronze_trips(spark: SparkSession, df: DataFrame) -> None:
    """Append validated and normalized raw trips to the bronze.yellow_taxi_trips table.

    Aligns incoming columns against the standard Bronze schema and fills missing
    optional columns with nulls.

    Args:
        spark: Active SparkSession.
        df: Enriched Bronze DataFrame.
    """
    config = load_config()
    bronze_cols = [
        "source_file",
        "source_month",
        "ingestion_run_id",
        "ingested_at",
        "vendor_id",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "passenger_count",
        "trip_distance",
        "rate_code_id",
        "store_and_fwd_flag",
        "pickup_location_id",
        "dropoff_location_id",
        "payment_type",
        "fare_amount",
        "extra",
        "mta_tax",
        "tip_amount",
        "tolls_amount",
        "improvement_surcharge",
        "total_amount",
        "congestion_surcharge",
        "airport_fee",
        "cbd_congestion_fee",
    ]
    existing = set(df.columns)
    selected = [c for c in bronze_cols if c in existing]
    out = df.select(*selected)
    for col in bronze_cols:
        if col not in existing:
            out = out.withColumn(col, F.lit(None))
    out = out.select(*bronze_cols)
    out.write.format("delta").mode("append").saveAsTable(
        _fqn(config, config.bronze_schema, "yellow_taxi_trips")
    )


def overwrite_silver_partition(spark: SparkSession, df: DataFrame, source_month: str) -> None:
    """Atomically replace Silver trips for a specific source_month partition.

    Deletes existing rows for source_month and appends new validated trips to ensure
    idempotent reruns.

    Args:
        spark: Active SparkSession.
        df: Validated Silver trips DataFrame.
        source_month: Target partition month string (YYYY-MM).
    """
    config = load_config()
    table = _fqn(config, config.silver_schema, "trips")
    spark.sql(f"DELETE FROM {table} WHERE source_month = '{source_month}'")
    df.write.format("delta").mode("append").saveAsTable(table)


def merge_gold_hourly(spark: SparkSession, df: DataFrame) -> None:
    """Upsert hourly pickup aggregates into gold.fact_pickups_hourly.

    Matches on (pickup_hour, pickup_zone_id): updates pickup_count and processed_at
    if matched, or inserts new rows if not matched.

    Args:
        spark: Active SparkSession.
        df: Hourly aggregated DataFrame.
    """
    config = load_config()
    table = _fqn(config, config.gold_schema, "fact_pickups_hourly")
    df.createOrReplaceTempView("incoming_hourly")
    spark.sql(
        f"""
        MERGE INTO {table} AS t
        USING incoming_hourly AS s
        ON t.pickup_hour = s.pickup_hour AND t.pickup_zone_id = s.pickup_zone_id
        WHEN MATCHED THEN UPDATE SET
          pickup_count = s.pickup_count,
          processed_at = s.processed_at
        WHEN NOT MATCHED THEN INSERT *
        """
    )
