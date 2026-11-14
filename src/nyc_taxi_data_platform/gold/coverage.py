"""Gold layer complete hourly coverage grid and zero-filling.

Constructs a Cartesian product of all taxi zones and all hours in a date range,
left-joining observed pickups and filling unobserved zone-hours with zero.
"""

from __future__ import annotations

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F


def build_hourly_grid(
    spark: SparkSession,
    zone_ids: list[int],
    start_ts: str,
    end_ts: str,
) -> DataFrame:
    """Generate a dense hourly grid cross-joining all known taxi zones across a date range.

    Generates an uninterrupted sequence of hours between start_ts and end_ts,
    and cross joins with the specified zone IDs.

    Args:
        spark: Active SparkSession.
        zone_ids: List of integer zone IDs to include.
        start_ts: Start timestamp string (e.g. '2023-01-01 00:00:00').
        end_ts: End timestamp string (e.g. '2023-01-31 23:00:00').

    Returns:
        DataFrame with columns: pickup_hour, pickup_zone_id.
    """
    zones_df = spark.createDataFrame([(int(z),) for z in zone_ids], "pickup_zone_id int")
    hours_df = spark.sql(
        f"""
        SELECT explode(sequence(
            date_trunc('hour', timestamp '{start_ts}'),
            date_trunc('hour', timestamp '{end_ts}'),
            interval 1 hour
        )) AS pickup_hour
        """
    )
    return hours_df.crossJoin(zones_df)


def apply_zero_fill(observed: DataFrame, grid: DataFrame) -> DataFrame:
    """Left join observed pickup counts onto the complete coverage grid, filling nulls with zero.

    This ensures that hours with zero pickups for a zone are explicitly represented as 0,
    preventing missing timestamps in time-series forecasting.

    Args:
        observed: Aggregated observed pickups DataFrame (pickup_hour, pickup_zone_id, pickup_count).
        grid: Dense coverage grid DataFrame (pickup_hour, pickup_zone_id).

    Returns:
        Zero-filled DataFrame with complete zone-hour rows.
    """
    return (
        grid.join(observed, on=["pickup_hour", "pickup_zone_id"], how="left")
        .select(
            F.col("pickup_hour"),
            F.col("pickup_zone_id"),
            F.coalesce(F.col("pickup_count"), F.lit(0)).alias("pickup_count"),
            F.coalesce(F.col("processed_at"), F.current_timestamp()).alias("processed_at"),
        )
    )
