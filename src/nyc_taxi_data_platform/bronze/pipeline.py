"""Bronze layer Spark reading and column validation pipeline.

Reads incoming Parquet files, verifies schema conformity against era rules,
normalizes column names to canonical snake_case, and appends ingestion metadata.
"""

from __future__ import annotations

from datetime import datetime, timezone

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F

from nyc_taxi_data_platform.bronze.ingest import infer_source_month, source_file_identity
from nyc_taxi_data_platform.sources.schema_registry import normalize_column_name
from nyc_taxi_data_platform.sources.validation import ValidationStatus, validate_source_columns


def read_parquet_with_validation(
    spark: SparkSession, path: str
) -> tuple[DataFrame | None, dict]:
    """Read Parquet file and validate required columns and schema era.

    Args:
        spark: Active SparkSession.
        path: File path of the Parquet dataset to read.

    Returns:
        Tuple of:
            - DataFrame with normalized column names and added metadata (or None if invalid).
            - Dictionary containing manifest attributes (identity, status, record count, error message).
    """
    try:
        df = spark.read.parquet(path)
    except Exception as exc:  # noqa: BLE001 - surface corrupt file as manifest status
        return None, {
            "processing_status": "corrupted_file",
            "error_message": str(exc),
            "record_count": 0,
        }

    # Validate source columns against supported modern schema eras
    result = validate_source_columns(df.columns)
    if result.status != ValidationStatus.OK:
        status = (
            "unsupported_schema"
            if result.status == ValidationStatus.UNSUPPORTED_SCHEMA
            else "schema_mismatch"
        )
        return None, {
            "processing_status": status,
            "error_message": result.message,
            "record_count": 0,
        }

    # Normalize column names to canonical snake_case
    renamed = df
    for col in df.columns:
        target = normalize_column_name(col)
        if target != col:
            renamed = renamed.withColumnRenamed(col, target)

    count = renamed.count()
    now = datetime.now(timezone.utc)
    month = infer_source_month(path)
    run_id = F.lit("local-run")

    # Enrich with ingestion lineage metadata
    enriched = (
        renamed.withColumn("source_file", F.lit(path))
        .withColumn("source_month", F.lit(month))
        .withColumn("ingestion_run_id", run_id)
        .withColumn("ingested_at", F.lit(now))
    )
    identity = source_file_identity(path, None)

    return enriched, {
        "source_file_identity": identity,
        "source_file": path,
        "source_month": month,
        "processing_status": "ingested",
        "error_message": None,
        "record_count": count,
    }
