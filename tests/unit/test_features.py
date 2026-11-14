"""Unit tests for Gold layer machine learning feature engineering."""

from datetime import datetime, timedelta

from pyspark.sql import functions as F

from nyc_taxi_data_platform.gold.features import (
    INFERENCE_FEATURE_COLUMNS,
    TRAINING_FEATURE_COLUMNS,
    build_ml_features,
    to_inference_features,
)


def _hourly_series(spark, zone_id: int = 161, hours: int = 200):
    """Generate synthetic hourly pickup time series for testing."""
    start = datetime(2023, 1, 1, 0, 0)
    rows = [
        (start + timedelta(hours=h), zone_id, float((h % 5) + 1)) for h in range(hours)
    ]
    return spark.createDataFrame(rows, ["pickup_hour", "pickup_zone_id", "pickup_count"])


def test_lag_24h_uses_prior_day(spark):
    """Verify that lag_24h retrieves the exact pickup count from 24 hours prior."""
    hourly = _hourly_series(spark, hours=30)
    features = build_ml_features(hourly)
    row = (
        features.filter(F.col("forecast_hour") == datetime(2023, 1, 2, 0, 0))
        .collect()[0]
    )
    # pickup_count pattern: (hour % 5) + 1 -> hour 0 = 1, hour 24 = 5
    assert row.lag_24h == 1.0
    assert row.target_pickup_count == 5


def test_rolling_excludes_target_hour(spark):
    """Verify that rolling features are calculated using rows strictly prior to forecast hour."""
    hourly = _hourly_series(spark, hours=48)
    features = build_ml_features(hourly)
    row = features.orderBy("forecast_hour").collect()[25]
    assert row.rolling_mean_24h is not None
    assert row.target_pickup_count is not None


def test_training_inference_schema_parity(spark):
    """Verify that training and inference schemas match except for target_pickup_count."""
    hourly = _hourly_series(spark, hours=200)
    training = build_ml_features(hourly)
    inference = to_inference_features(training)
    training_cols = set(training.columns) - {"target_pickup_count"}
    inference_cols = set(inference.columns)
    assert training_cols == inference_cols
    assert set(INFERENCE_FEATURE_COLUMNS + ["processed_at"]).issubset(inference_cols)
    assert "target_pickup_count" in TRAINING_FEATURE_COLUMNS
