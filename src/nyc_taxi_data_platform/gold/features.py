"""Machine learning feature engineering from hourly pickup facts.

Builds calendar features, historical lags (1h, 24h, 168h), and rolling statistics
(24h mean, 168h mean, 24h std) partitioned by taxi zone. Ensures strict temporal
isolation to prevent target data leakage (using rowsBetween -N, -1).
"""

from __future__ import annotations

from pyspark.sql import DataFrame, Window
from pyspark.sql import functions as F

# Ordered feature column names used for ML model training
TRAINING_FEATURE_COLUMNS = [
    "pickup_zone_id",
    "forecast_hour",
    "hour_of_day",
    "day_of_week",
    "day_of_month",
    "month",
    "is_weekend",
    "lag_1h",
    "lag_24h",
    "lag_168h",
    "rolling_mean_24h",
    "rolling_mean_168h",
    "rolling_std_24h",
    "target_pickup_count",
]

# Ordered feature column names for inference (excludes target_pickup_count)
INFERENCE_FEATURE_COLUMNS = [c for c in TRAINING_FEATURE_COLUMNS if c != "target_pickup_count"]


def _partition_window() -> Window:
    """Return Window partitioned by zone and ordered by forecast hour."""
    return Window.partitionBy("pickup_zone_id").orderBy("forecast_hour")


def build_ml_features(hourly: DataFrame) -> DataFrame:
    """Construct training features per (zone, hour).

    Features generated:
        - Calendar: hour_of_day, day_of_week, day_of_month, month, is_weekend
        - Lags: lag_1h, lag_24h, lag_168h (1 week prior)
        - Rolling: 24h rolling average, 168h rolling average, 24h rolling std

    Important: All lags and rolling statistics use only strictly prior hours
    (excluding the target forecast hour) to prevent lookahead data leakage.

    Args:
        hourly: Input hourly fact DataFrame (pickup_hour, pickup_zone_id, pickup_count).

    Returns:
        Feature-enriched DataFrame matching TRAINING_FEATURE_COLUMNS schema.
    """
    base = (
        hourly.withColumnRenamed("pickup_hour", "forecast_hour")
        .withColumn("pickup_zone_id", F.col("pickup_zone_id").cast("int"))
        .withColumn("pickup_count", F.col("pickup_count").cast("double"))
    )

    w = _partition_window()
    prior = base.withColumn("prior_pickup_count", F.col("pickup_count"))

    featured = (
        prior.withColumn("hour_of_day", F.hour("forecast_hour"))
        .withColumn("day_of_week", F.dayofweek("forecast_hour"))
        .withColumn("day_of_month", F.dayofmonth("forecast_hour"))
        .withColumn("month", F.month("forecast_hour"))
        .withColumn(
            "is_weekend",
            F.dayofweek("forecast_hour").isin([1, 7]),
        )
        .withColumn(
            "lag_1h",
            F.lag("prior_pickup_count", 1).over(w),
        )
        .withColumn(
            "lag_24h",
            F.lag("prior_pickup_count", 24).over(w),
        )
        .withColumn(
            "lag_168h",
            F.lag("prior_pickup_count", 168).over(w),
        )
        .withColumn(
            "rolling_mean_24h",
            F.avg("prior_pickup_count").over(w.rowsBetween(-24, -1)),
        )
        .withColumn(
            "rolling_mean_168h",
            F.avg("prior_pickup_count").over(w.rowsBetween(-168, -1)),
        )
        .withColumn(
            "rolling_std_24h",
            F.stddev_samp("prior_pickup_count").over(w.rowsBetween(-24, -1)),
        )
        .withColumn("target_pickup_count", F.col("pickup_count").cast("long"))
        .withColumn("processed_at", F.current_timestamp())
        .drop("prior_pickup_count", "pickup_count")
    )
    return featured


def to_inference_features(training: DataFrame) -> DataFrame:
    """Project training features DataFrame to inference features by omitting the target label.

    Args:
        training: Training features DataFrame containing target_pickup_count.

    Returns:
        Inference features DataFrame.
    """
    return training.select(
        *[c for c in INFERENCE_FEATURE_COLUMNS],
        F.col("processed_at"),
    )
