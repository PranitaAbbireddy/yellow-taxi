"""Unit tests for Silver layer standardization, quarantine, and deduplication."""

from pyspark.sql import functions as F

from nyc_taxi_data_platform.bronze.pipeline import read_parquet_with_validation
from nyc_taxi_data_platform.config import load_config
from nyc_taxi_data_platform.silver.transform import (
    deduplicate_trips,
    split_valid_and_quarantine,
    standardize_bronze_trips,
)
from nyc_taxi_data_platform.silver.zones import standardize_zone_lookup


def test_quarantine_invalid_dropoff_before_pickup(spark, modern_parquet_path):
    """Verify that records with dropoff timestamp preceding pickup are sent to quarantine."""
    config = load_config()
    bronze, _ = read_parquet_with_validation(spark, modern_parquet_path)
    assert bronze is not None
    bronze = bronze.withColumn(
        "tpep_dropoff_datetime",
        F.lit("2020-01-01 00:00:00").cast("timestamp"),
    )
    standardized = standardize_bronze_trips(bronze, config.local_timezone)
    valid, quarantined = split_valid_and_quarantine(standardized, config.quality)
    assert valid.count() == 0
    assert quarantined.count() == 2


def test_deduplicate_trips(spark, modern_parquet_path):
    """Verify that duplicate rows with identical fingerprints are deduplicated."""
    config = load_config()
    bronze, _ = read_parquet_with_validation(spark, modern_parquet_path)
    standardized = standardize_bronze_trips(bronze, config.local_timezone)
    duplicated = standardized.unionByName(standardized)
    deduped = deduplicate_trips(duplicated)
    assert deduped.count() == standardized.count()


def test_zone_lookup_standardize(spark):
    """Verify that raw zone lookup CSV columns are normalized to Silver schema."""
    df = spark.createDataFrame(
        [(1, "EWR", "Newark Airport", "EWR")],
        ["LocationID", "Borough", "Zone", "service_zone"],
    )
    out = standardize_zone_lookup(df)
    row = out.collect()[0]
    assert row.zone_id == 1
    assert row.borough == "EWR"
