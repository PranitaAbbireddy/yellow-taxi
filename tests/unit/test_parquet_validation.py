"""Unit tests for Parquet column validation without Spark dependencies."""

import pyarrow.parquet as pq

from nyc_taxi_data_platform.sources.validation import ValidationStatus, validate_source_columns


def test_modern_parquet_columns(modern_parquet_path):
    """Verify that modern Parquet schemas containing required columns pass validation."""
    columns = pq.read_schema(modern_parquet_path).names
    result = validate_source_columns(columns)
    assert result.status == ValidationStatus.OK


def test_missing_datetime_parquet_columns(missing_datetime_parquet):
    """Verify that schemas missing pickup datetime are flagged as MISSING_REQUIRED."""
    columns = pq.read_schema(missing_datetime_parquet).names
    result = validate_source_columns(columns)
    assert result.status == ValidationStatus.MISSING_REQUIRED


def test_pre2011_parquet_columns(pre2011_parquet):
    """Verify that pre-2011 coordinate-based schemas are rejected as UNSUPPORTED_SCHEMA."""
    columns = pq.read_schema(pre2011_parquet).names
    result = validate_source_columns(columns)
    assert result.status == ValidationStatus.UNSUPPORTED_SCHEMA
