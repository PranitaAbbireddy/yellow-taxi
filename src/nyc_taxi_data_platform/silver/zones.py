"""Taxi zone reference lookup standardization.

Normalizes TLC taxi zone CSV/Parquet reference data into the Silver taxi_zones schema.
"""

from __future__ import annotations

from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def standardize_zone_lookup(df: DataFrame) -> DataFrame:
    """Normalize TLC taxi zone lookup columns to silver.taxi_zones schema.

    Handles case-insensitive column variations across different TLC releases
    (e.g. LocationID vs location_id, Zone vs zone).

    Args:
        df: Input DataFrame containing raw zone lookup records.

    Returns:
        Standardized DataFrame with columns:
            zone_id (int), borough (string), zone_name (string), service_zone (string), processed_at (timestamp).
    """
    cols = {c.lower(): c for c in df.columns}
    loc = cols.get("locationid") or cols.get("location_id")
    borough = cols.get("borough")
    zone = cols.get("zone")
    service = cols.get("service_zone") or cols.get("servicezone")

    return df.select(
        F.col(loc).cast("int").alias("zone_id"),
        F.col(borough).alias("borough"),
        F.col(zone).alias("zone_name"),
        F.col(service).alias("service_zone"),
        F.current_timestamp().alias("processed_at"),
    )
