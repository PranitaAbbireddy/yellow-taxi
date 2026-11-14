"""Export Gold tables as single-part CSV files for downstream notebooks and apps.

Writes each Gold table to a single named CSV file under a Unity Catalog volume
so the CSV-backed dashboard and local agent can be refreshed whenever the pipeline
runs. Volumes do not support non-sequential writes directly, so files are staged
on local disk and then copied into the target volume path.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

from pyspark.sql import SparkSession

from nyc_taxi_data_platform.config import PipelineConfig

# Set of Gold tables required by the downstream notebook, dashboard, and evaluation script
GOLD_EXPORT_TABLES = (
    "dim_taxi_zone",
    "fact_pickups_hourly",
    "ml_training_features",
    "ml_inference_features",
)


def ensure_exports_volume(spark: SparkSession, config: PipelineConfig) -> str:
    """Create the Gold exports volume if missing and return its /Volumes POSIX path.

    Args:
        spark: Active SparkSession.
        config: Pipeline configuration containing catalog and schema names.

    Returns:
        String path to the Unity Catalog volume (e.g. '/Volumes/nyc_taxi/gold/exports').
    """
    spark.sql(
        f"CREATE VOLUME IF NOT EXISTS {config.catalog}.{config.gold_schema}.exports"
    )
    return f"/Volumes/{config.catalog}/{config.gold_schema}/exports"


def export_table_csv(spark: SparkSession, fqn: str, out_path: str) -> int:
    """Read a Delta table and export it as a single CSV file at out_path.

    Staging via a temporary directory ensures safe sequential writing into UC Volumes.

    Args:
        spark: Active SparkSession.
        fqn: Fully qualified table name (catalog.schema.table).
        out_path: Destination file path.

    Returns:
        Total number of rows exported.
    """
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
    """Export every Gold table consumed downstream; returns dictionary of table row counts.

    Args:
        spark: Active SparkSession.
        config: Current pipeline configuration.
        export_root: Optional custom destination folder path (defaults to UC volume).

    Returns:
        Mapping of table name to exported row count.
    """
    root = export_root or ensure_exports_volume(spark, config)
    results: dict[str, int] = {}
    for table in GOLD_EXPORT_TABLES:
        fqn = config.table_fqn(config.gold_schema, table)
        results[table] = export_table_csv(spark, fqn, f"{root}/{table}.csv")
    return results
