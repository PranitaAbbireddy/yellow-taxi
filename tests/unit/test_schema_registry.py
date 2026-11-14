"""Unit tests for schema era detection and canonical column normalization."""

from nyc_taxi_data_platform.sources.schema_registry import (
    SchemaEra,
    detect_era,
    normalize_column_name,
)


def test_normalize_pascal_case():
    """Verify normalization of PascalCase TLC column names to canonical snake_case."""
    assert normalize_column_name("PULocationID") == "pickup_location_id"
    assert normalize_column_name("VendorID") == "vendor_id"


def test_detect_modern_era():
    """Verify that presence of congestion_surcharge identifies POST_CONGESTION era."""
    cols = {
        "vendor_id",
        "tpep_pickup_datetime",
        "pickup_location_id",
        "dropoff_location_id",
        "congestion_surcharge",
    }
    assert detect_era(cols) == SchemaEra.POST_CONGESTION


def test_detect_pre_2011():
    """Verify that presence of coordinate marker columns identifies PRE_2011 era."""
    cols = {
        "pickup_longitude",
        "pickup_latitude",
        "dropoff_longitude",
        "dropoff_latitude",
        "tpep_pickup_datetime",
    }
    assert detect_era(cols) == SchemaEra.PRE_2011
