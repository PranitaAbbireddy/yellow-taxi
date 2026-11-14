"""Gold layer hourly pickup aggregation and data quality reconciliation.

Groups accepted Silver trips into hourly pickup counts per taxi zone and computes
reconciliation check statistics.
"""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def hourly_pickups_from_silver(trips: DataFrame) -> DataFrame:
    """Aggregate accepted Silver trips into (pickup_hour, pickup_zone_id) counts.

    Truncates pickup timestamps to the hour and groups by zone to create the primary
    hourly pickup fact table.

    Args:
        trips: Valid Silver trips DataFrame.

    Returns:
        DataFrame with columns: pickup_hour, pickup_zone_id, pickup_count, processed_at.
    """
    return (
        trips.withColumn("pickup_hour", F.date_trunc("hour", F.col("pickup_datetime")))
        .withColumn("pickup_zone_id", F.col("pickup_zone_id").cast("int"))
        .groupBy("pickup_hour", F.col("pickup_zone_id"))
        .agg(F.count(F.lit(1)).alias("pickup_count"))
        .withColumn("processed_at", F.current_timestamp())
    )


def reconcile_counts(silver_trips: DataFrame, gold_hourly: DataFrame) -> dict[str, int]:
    """Perform count reconciliation between Silver input trips and Gold hourly aggregates.

    Ensures that the total sum of pickup_count in Gold equals the row count of valid Silver trips.

    Args:
        silver_trips: Valid Silver trips DataFrame.
        gold_hourly: Aggregated Gold hourly pickups DataFrame.

    Returns:
        Dictionary with 'silver_trip_count' and 'gold_pickup_sum'.
    """
    silver_count = silver_trips.count()
    gold_sum = gold_hourly.agg(F.sum("pickup_count")).collect()[0][0] or 0
    return {"silver_trip_count": silver_count, "gold_pickup_sum": int(gold_sum)}
