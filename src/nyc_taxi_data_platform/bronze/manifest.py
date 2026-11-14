"""Ingestion manifest tracking for idempotent file loading.

Maintains an audit trail of ingested files, row counts, and error statuses to
prevent duplicate processing.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import types as T

# Standard Spark schema for the ingestion_manifest table
MANIFEST_SCHEMA = T.StructType(
    [
        T.StructField("source_file_identity", T.StringType(), False),
        T.StructField("source_file", T.StringType(), False),
        T.StructField("source_month", T.StringType(), False),
        T.StructField("ingestion_run_id", T.StringType(), False),
        T.StructField("ingested_at", T.TimestampType(), False),
        T.StructField("record_count", T.LongType(), True),
        T.StructField("processing_status", T.StringType(), False),
        T.StructField("error_message", T.StringType(), True),
    ]
)


@dataclass(frozen=True)
class ManifestRecord:
    """Record representing a single file ingestion attempt.

    Attributes:
        source_file_identity: Deterministic hash of source path and size.
        source_file: Original file path.
        source_month: Partition month (YYYY-MM).
        ingestion_run_id: Pipeline run UUID.
        ingested_at: Timestamp of ingestion attempt.
        record_count: Number of rows ingested.
        processing_status: Status outcome ('ingested', 'duplicate', 'corrupted_file', 'schema_mismatch').
        error_message: Optional error explanation.
    """

    source_file_identity: str
    source_file: str
    source_month: str
    ingestion_run_id: str
    ingested_at: datetime
    record_count: int
    processing_status: str
    error_message: str | None = None


def manifest_to_spark_df(spark: SparkSession, manifest: ManifestRecord) -> DataFrame:
    """Convert a ManifestRecord dataclass instance into a single-row Spark DataFrame.

    Args:
        spark: Active SparkSession.
        manifest: ManifestRecord instance.

    Returns:
        DataFrame conforming to MANIFEST_SCHEMA.
    """
    row = (
        manifest.source_file_identity,
        manifest.source_file,
        manifest.source_month,
        manifest.ingestion_run_id,
        manifest.ingested_at,
        int(manifest.record_count),
        manifest.processing_status,
        manifest.error_message,
    )
    return spark.createDataFrame([row], schema=MANIFEST_SCHEMA)


def is_duplicate(identity: str, known_identities: set[str]) -> bool:
    """Check whether a file identity has already been recorded in the manifest."""
    return identity in known_identities


def apply_duplicate_policy(
    manifest: ManifestRecord, known_identities: set[str]
) -> ManifestRecord:
    """Evaluate duplicate policy and update manifest status if already processed.

    Args:
        manifest: Incoming ManifestRecord candidate.
        known_identities: Set of previously ingested file identities.

    Returns:
        Original ManifestRecord if new, or updated ManifestRecord marked as 'duplicate'.
    """
    if is_duplicate(manifest.source_file_identity, known_identities):
        return ManifestRecord(
            source_file_identity=manifest.source_file_identity,
            source_file=manifest.source_file,
            source_month=manifest.source_month,
            ingestion_run_id=manifest.ingestion_run_id,
            ingested_at=manifest.ingested_at,
            record_count=0,
            processing_status="duplicate",
            error_message="Source file identity already ingested.",
        )
    return manifest
