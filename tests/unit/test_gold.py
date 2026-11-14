"""Unit tests for Gold layer aggregation, zero-filling, and count reconciliation."""

from datetime import datetime

from pyspark.sql import functions as F

from nyc_taxi_data_platform.bronze.pipeline import read_parquet_with_validation
from nyc_taxi_data_platform.config import load_config
from nyc_taxi_data_platform.gold.aggregates import hourly_pickups_from_silver, reconcile_counts
from nyc_taxi_data_platform.gold.coverage import apply_zero_fill, build_hourly_grid
from nyc_taxi_data_platform.silver.transform import standardize_bronze_trips


def test_hourly_aggregation_and_reconciliation(spark, modern_parquet_path):
    """Verify that hourly pickup sums reconcile exactly with valid Silver trip counts."""
    config = load_config()
    bronze, _ = read_parquet_with_validation(spark, modern_parquet_path)
    silver = standardize_bronze_trips(bronze, config.local_timezone)
    hourly = hourly_pickups_from_silver(silver)
    stats = reconcile_counts(silver, hourly)
    assert stats["silver_trip_count"] == stats["gold_pickup_sum"]


def test_zero_fill_within_coverage(spark):
    """Verify that unobserved zone-hours within coverage range are filled with 0."""
    observed = spark.createDataFrame(
        [
            (datetime(2023, 1, 1, 10, 0), 161, 2),
        ],
        ["pickup_hour", "pickup_zone_id", "pickup_count"],
    ).withColumn("processed_at", F.current_timestamp())

    grid = build_hourly_grid(
        spark,
        [161],
        "2023-01-01 10:00:00",
        "2023-01-01 11:00:00",
    )
    filled = apply_zero_fill(observed, grid)
    rows = {r.pickup_hour.hour: r.pickup_count for r in filled.collect()}
    assert rows[10] == 2
    assert rows[11] == 0
