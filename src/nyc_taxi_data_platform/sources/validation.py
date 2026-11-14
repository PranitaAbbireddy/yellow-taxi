"""Source file schema validation prior to Bronze ingestion.

Validates column presence and era compatibility, ensuring that mandatory columns
exist before ingesting TLC Parquet datasets.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from nyc_taxi_data_platform.sources.schema_registry import (
    MODERN_REQUIRED_COLUMNS,
    SchemaEra,
    detect_era,
    is_modern_era_supported,
    normalize_column_names,
)


class ValidationStatus(str, Enum):
    """Status outcomes for source column schema validation."""

    OK = "ok"
    MISSING_REQUIRED = "missing_required"
    EXTRA_COLUMNS = "extra_columns"
    ERA_MISMATCH = "era_mismatch"
    UNSUPPORTED_SCHEMA = "unsupported_schema"


@dataclass(frozen=True)
class SchemaValidationResult:
    """Detailed result of schema validation checks.

    Attributes:
        status: ValidationStatus enum outcome.
        era: Detected TLC SchemaEra.
        normalized_columns: Tuple of all normalized columns present.
        missing_required: Tuple of mandatory columns missing from the file.
        message: Explanatory validation message.
    """

    status: ValidationStatus
    era: SchemaEra
    normalized_columns: tuple[str, ...]
    missing_required: tuple[str, ...]
    message: str


def validate_source_columns(columns: list[str]) -> SchemaValidationResult:
    """Validate incoming dataset columns against modern schema requirements.

    Args:
        columns: List of raw column names extracted from source file.

    Returns:
        SchemaValidationResult detailing status, detected era, and missing columns.
    """
    normalized = normalize_column_names(columns)
    normalized_set = set(normalized)
    era = detect_era(normalized_set)

    # Reject pre-2011 lat/lon datasets early
    if not is_modern_era_supported(era):
        return SchemaValidationResult(
            status=ValidationStatus.UNSUPPORTED_SCHEMA,
            era=era,
            normalized_columns=tuple(sorted(normalized_set)),
            missing_required=tuple(),
            message=(
                "Pre-2011 lat/lon schema is documented but not supported in pipeline v1. "
                "Upload post-2011 Yellow Taxi Parquet with zone IDs."
            ),
        )

    # Check for missing required columns
    missing = sorted(MODERN_REQUIRED_COLUMNS - normalized_set)
    if missing:
        return SchemaValidationResult(
            status=ValidationStatus.MISSING_REQUIRED,
            era=era,
            normalized_columns=tuple(sorted(normalized_set)),
            missing_required=tuple(missing),
            message=f"Missing required columns: {', '.join(missing)}",
        )

    return SchemaValidationResult(
        status=ValidationStatus.OK,
        era=era,
        normalized_columns=tuple(sorted(normalized_set)),
        missing_required=tuple(),
        message="Schema validation passed.",
    )
