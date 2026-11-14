"""Configuration management for NYC Taxi Data Platform.

Loads configuration settings from YAML files and environment variable overrides,
supporting customizable catalogs, schemas, data quality bounds, and feature warmup windows.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

# Default configuration path pointing to config/defaults.yaml
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[2] / "config" / "defaults.yaml"


@dataclass(frozen=True)
class QualityConfig:
    """Threshold configurations for Silver data quality validation.

    Attributes:
        max_trip_distance_miles: Maximum acceptable trip distance in miles.
        min_fare_amount: Minimum acceptable fare amount in dollars (negative allows refunds).
        max_fare_amount: Maximum acceptable fare amount in dollars.
    """

    max_trip_distance_miles: float = 500.0
    min_fare_amount: float = -500.0
    max_fare_amount: float = 10000.0


@dataclass(frozen=True)
class FeatureConfig:
    """Settings for Gold feature engineering.

    Attributes:
        warmup_hours: Number of initial hours allocated for lag and rolling calculations.
    """

    warmup_hours: int = 168


@dataclass(frozen=True)
class PipelineConfig:
    """Complete pipeline execution and schema configuration.

    Attributes:
        catalog: Target Unity Catalog name (e.g. 'nyc_taxi' or 'workspace').
        bronze_schema: Bronze raw data schema name.
        silver_schema: Silver cleaned/quarantined schema name.
        gold_schema: Gold aggregated business tables and features schema name.
        volume_base: Base path for Unity Catalog volumes containing raw files.
        source_months: List of YYYY-MM strings indicating partition months to process.
        source_files: Explicit list of source file paths if specified.
        local_timezone: Target timezone for trip wall-clock timestamp normalization.
        coverage_start_date: Start date (YYYY-MM-DD) for complete hourly grid zero-filling.
        coverage_end_date: End date (YYYY-MM-DD) for complete hourly grid zero-filling.
        quality: QualityConfig instance holding trip validation bounds.
        features: FeatureConfig instance holding feature engineering settings.
    """

    catalog: str
    bronze_schema: str
    silver_schema: str
    gold_schema: str
    volume_base: str
    source_months: list[str]
    source_files: list[str]
    local_timezone: str
    coverage_start_date: str | None
    coverage_end_date: str | None
    quality: QualityConfig
    features: FeatureConfig

    def table_fqn(self, schema: str, table: str) -> str:
        """Construct a three-level fully qualified table name (catalog.schema.table)."""
        return f"{self.catalog}.{schema}.{table}"

    @property
    def bronze(self) -> str:
        """Shorthand accessor for bronze_schema."""
        return self.bronze_schema

    @property
    def silver(self) -> str:
        """Shorthand accessor for silver_schema."""
        return self.silver_schema

    @property
    def gold(self) -> str:
        """Shorthand accessor for gold_schema."""
        return self.gold_schema


def _coerce_list(value: Any) -> list[str]:
    """Helper to convert scalar or None values into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def load_config(path: Path | None = None) -> PipelineConfig:
    """Load and parse pipeline configuration from YAML file and environment variables.

    Environment variables override YAML settings:
        - NYC_TAXI_CATALOG overrides catalog
        - NYC_TAXI_VOLUME_BASE overrides volume_base

    Args:
        path: Optional Path to custom YAML configuration file.

    Returns:
        Fully populated PipelineConfig instance.
    """
    config_path = path or DEFAULT_CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        raw: dict[str, Any] = yaml.safe_load(handle) or {}

    schemas = raw.get("schemas") or {}
    quality_raw = raw.get("quality") or {}
    features_raw = raw.get("features") or {}

    # Environment variable overrides allow easy deployment across diverse workspaces
    catalog = os.environ.get("NYC_TAXI_CATALOG", raw.get("catalog", "nyc_taxi"))

    return PipelineConfig(
        catalog=catalog,
        bronze_schema=schemas.get("bronze", "bronze"),
        silver_schema=schemas.get("silver", "silver"),
        gold_schema=schemas.get("gold", "gold"),
        volume_base=os.environ.get("NYC_TAXI_VOLUME_BASE", raw.get("volume_base") or ""),
        source_months=_coerce_list(raw.get("source_months")),
        source_files=_coerce_list(raw.get("source_files")),
        local_timezone=raw.get("local_timezone", "America/New_York"),
        coverage_start_date=raw.get("coverage_start_date"),
        coverage_end_date=raw.get("coverage_end_date"),
        quality=QualityConfig(
            max_trip_distance_miles=float(
                quality_raw.get("max_trip_distance_miles", 500.0)
            ),
            min_fare_amount=float(quality_raw.get("min_fare_amount", -500.0)),
            max_fare_amount=float(quality_raw.get("max_fare_amount", 10000.0)),
        ),
        features=FeatureConfig(warmup_hours=int(features_raw.get("warmup_hours", 168))),
    )
