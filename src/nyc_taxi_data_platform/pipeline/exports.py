"""Export gold tables as CSV files for downstream notebooks and apps.

Writes each table to a single named CSV file under a Unity Catalog volume so
the CSV-backed dashboard/agent in this repository can be refreshed whenever
the pipeline runs. Volumes do not support non-sequential writes, so files are
staged on local disk and then copied into the volume.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from pyspark.sql import SparkSession

from nyc_taxi_data_platform.config import PipelineConfig

GOLD_EXPORT_TABLES = (
    "dim_taxi_zone",
    "fact_pickups_hourly",
    "ml_training_features",
    "ml_inference_features",
)


def ensure_exports_volume(spark: SparkSession, config: PipelineConfig) -> str:
    """Create the exports volume if missing and return its /Volumes path."""
    spark.sql(
        f"CREATE VOLUME IF NOT EXISTS {config.catalog}.{config.gold_schema}.exports"
    )
    return f"/Volumes/{config.catalog}/{config.gold_schema}/exports"


def export_table_csv(spark: SparkSession, fqn: str, out_path: str) -> int:
    """Write one table to a single CSV file at out_path. Returns row count."""
    df = spark.table(fqn)
    count = df.count()
    with tempfile.TemporaryDirectory() as tmpdir:
        local_file = Path(tmpdir) / "part.csv"
        df.toPandas().to_csv(local_file, index=False)
        shutil.copyfile(local_file, out_path)
    return count


def stage_export_gold_csv(
    spark: SparkSession,
    config: PipelineConfig,
    export_root: str | None = None,
) -> dict[str, int]:
    """Export every gold CSV consumed downstream; returns row counts."""
    root = export_root or ensure_exports_volume(spark, config)
    results: dict[str, int] = {}
    for table in GOLD_EXPORT_TABLES:
        fqn = config.table_fqn(config.gold_schema, table)
        results[table] = export_table_csv(spark, fqn, f"{root}/{table}.csv")
    return results
