"""Unit tests for Bronze layer Spark parquet reader."""

from nyc_taxi_data_platform.bronze.pipeline import read_parquet_with_validation


def test_read_modern_parquet(spark, modern_parquet_path):
    """Verify reading valid modern Parquet file returns DataFrame and ingested status."""
    df, manifest = read_parquet_with_validation(spark, modern_parquet_path)
    assert manifest["processing_status"] == "ingested"
    assert manifest["record_count"] == 2
    assert df is not None
    assert "pickup_location_id" in df.columns


def test_read_missing_columns(spark, missing_datetime_parquet):
    """Verify that file missing mandatory columns returns None DataFrame and schema_mismatch."""
    df, manifest = read_parquet_with_validation(spark, missing_datetime_parquet)
    assert df is None
    assert manifest["processing_status"] == "schema_mismatch"


def test_read_pre2011(spark, pre2011_parquet):
    """Verify that pre-2011 file returns None DataFrame and unsupported_schema status."""
    df, manifest = read_parquet_with_validation(spark, pre2011_parquet)
    assert df is None
    assert manifest["processing_status"] == "unsupported_schema"
