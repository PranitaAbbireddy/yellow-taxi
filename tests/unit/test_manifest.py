"""Unit tests for ingestion manifest duplicate detection policy."""

from datetime import datetime, timezone

from nyc_taxi_data_platform.bronze.manifest import (
    ManifestRecord,
    apply_duplicate_policy,
)

_NOW = datetime.now(timezone.utc)


def test_duplicate_ingestion_blocked():
    """Verify that an already-known file identity is marked as duplicate with 0 record count."""
    identity = "abc123"
    known = {identity}
    record = ManifestRecord(
        source_file_identity=identity,
        source_file="/vol/yellow_tripdata_2023-01.parquet",
        source_month="2023-01",
        ingestion_run_id="run-1",
        ingested_at=_NOW,
        record_count=100,
        processing_status="ingested",
    )
    out = apply_duplicate_policy(record, known)
    assert out.processing_status == "duplicate"
    assert out.record_count == 0


def test_reprocess_after_identity_removed():
    """Verify that removing an identity from known set allows file reprocessing."""
    identity = "abc123"
    record = ManifestRecord(
        source_file_identity=identity,
        source_file="/vol/yellow_tripdata_2023-01.parquet",
        source_month="2023-01",
        ingestion_run_id="run-2",
        ingested_at=_NOW,
        record_count=100,
        processing_status="ingested",
    )
    out = apply_duplicate_policy(record, set())
    assert out.processing_status == "ingested"
