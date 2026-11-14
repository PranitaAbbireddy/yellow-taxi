"""NYC TLC Yellow Taxi source schema eras and column normalization mappings.

Defines the evolution of NYC TLC Yellow Taxi schemas over time:
- PRE_2011: Legacy coordinate-based era (latitude/longitude coordinates, no zone IDs).
- POST_2011: Modern taxi zone era (PULocationID, DOLocationID).
- POST_CONGESTION: Introduction of congestion surcharge and airport fee.
- POST_2025: Addition of Manhattan Central Business District (CBD) congestion fee.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import FrozenSet


class SchemaEra(str, Enum):
    """Enumeration of recognized TLC Yellow Taxi schema eras."""

    PRE_2011 = "pre_2011"
    POST_2011 = "post_2011"
    POST_CONGESTION = "post_congestion"
    POST_2025 = "post_2025"


# Mapping from various TLC raw column names (PascalCase or legacy variants) to canonical snake_case
CANONICAL_RENAME_MAP: dict[str, str] = {
    "VendorID": "vendor_id",
    "vendorid": "vendor_id",
    "tpep_pickup_datetime": "tpep_pickup_datetime",
    "tpep_dropoff_datetime": "tpep_dropoff_datetime",
    "passenger_count": "passenger_count",
    "trip_distance": "trip_distance",
    "RatecodeID": "rate_code_id",
    "ratecodeid": "rate_code_id",
    "rate_code_id": "rate_code_id",
    "store_and_fwd_flag": "store_and_fwd_flag",
    "PULocationID": "pickup_location_id",
    "pickup_location_id": "pickup_location_id",
    "DOLocationID": "dropoff_location_id",
    "dropoff_location_id": "dropoff_location_id",
    "payment_type": "payment_type",
    "fare_amount": "fare_amount",
    "extra": "extra",
    "mta_tax": "mta_tax",
    "tip_amount": "tip_amount",
    "tolls_amount": "tolls_amount",
    "improvement_surcharge": "improvement_surcharge",
    "total_amount": "total_amount",
    "congestion_surcharge": "congestion_surcharge",
    "airport_fee": "airport_fee",
    "cbd_congestion_fee": "cbd_congestion_fee",
    "pickup_longitude": "pickup_longitude",
    "pickup_latitude": "pickup_latitude",
    "dropoff_longitude": "dropoff_longitude",
    "dropoff_latitude": "dropoff_latitude",
}

# Minimum set of columns strictly required for modern zone-based pipeline processing
MODERN_REQUIRED_COLUMNS: FrozenSet[str] = frozenset(
    {
        "vendor_id",
        "tpep_pickup_datetime",
        "tpep_dropoff_datetime",
        "pickup_location_id",
        "dropoff_location_id",
        "trip_distance",
        "fare_amount",
    }
)

# Marker columns identifying the pre-2011 latitude/longitude era
PRE_2011_MARKER_COLUMNS: FrozenSet[str] = frozenset(
    {
        "pickup_longitude",
        "pickup_latitude",
        "dropoff_longitude",
        "dropoff_latitude",
    }
)

# Marker columns identifying post-2011 zone-based schemas
POST_2011_ZONE_COLUMNS: FrozenSet[str] = frozenset(
    {"pickup_location_id", "dropoff_location_id"}
)


@dataclass(frozen=True)
class EraDefinition:
    """Metadata describing a TLC schema era.

    Attributes:
        era: SchemaEra enum value.
        description: Textual explanation of era features.
        optional_columns: Additional columns characteristic of this era.
    """

    era: SchemaEra
    description: str
    optional_columns: FrozenSet[str]


ERA_DEFINITIONS: dict[SchemaEra, EraDefinition] = {
    SchemaEra.PRE_2011: EraDefinition(
        era=SchemaEra.PRE_2011,
        description="Lat/lon locations; no TLC zone IDs.",
        optional_columns=frozenset(
            {
                "rate_code_id",
                "store_and_fwd_flag",
                "passenger_count",
                "payment_type",
                "extra",
                "mta_tax",
                "tip_amount",
                "tolls_amount",
                "total_amount",
            }
        ),
    ),
    SchemaEra.POST_2011: EraDefinition(
        era=SchemaEra.POST_2011,
        description="Zone IDs; improvement_surcharge from ~2015.",
        optional_columns=frozenset(
            {
                "passenger_count",
                "rate_code_id",
                "store_and_fwd_flag",
                "payment_type",
                "extra",
                "mta_tax",
                "tip_amount",
                "tolls_amount",
                "improvement_surcharge",
                "total_amount",
            }
        ),
    ),
    SchemaEra.POST_CONGESTION: EraDefinition(
        era=SchemaEra.POST_CONGESTION,
        description="Adds congestion_surcharge and airport_fee.",
        optional_columns=frozenset({"congestion_surcharge", "airport_fee"}),
    ),
    SchemaEra.POST_2025: EraDefinition(
        era=SchemaEra.POST_2025,
        description="Adds cbd_congestion_fee (Jan 2025+).",
        optional_columns=frozenset({"cbd_congestion_fee"}),
    ),
}


def normalize_column_name(name: str) -> str:
    """Normalize raw TLC column name to its canonical snake_case representation."""
    return CANONICAL_RENAME_MAP.get(name, CANONICAL_RENAME_MAP.get(name.lower(), name.lower()))


def normalize_column_names(columns: list[str]) -> list[str]:
    """Normalize a list of raw column names to canonical snake_case."""
    return [normalize_column_name(c) for c in columns]


def detect_era(normalized_columns: set[str]) -> SchemaEra:
    """Detect schema era based on the presence of characteristic marker columns.

    Args:
        normalized_columns: Set of canonical column names present in the file.

    Returns:
        Identified SchemaEra.
    """
    has_latlon = PRE_2011_MARKER_COLUMNS.issubset(normalized_columns)
    has_zones = POST_2011_ZONE_COLUMNS.issubset(normalized_columns)

    if has_latlon and not has_zones:
        return SchemaEra.PRE_2011
    if "cbd_congestion_fee" in normalized_columns:
        return SchemaEra.POST_2025
    if "congestion_surcharge" in normalized_columns or "airport_fee" in normalized_columns:
        return SchemaEra.POST_CONGESTION
    return SchemaEra.POST_2011


def is_modern_era_supported(era: SchemaEra) -> bool:
    """Check if the detected schema era is supported by the zone-based pipeline.

    Pipeline v1 requires zone ID columns and does not ingest pre-2011 lat/lon datasets.
    """
    return era != SchemaEra.PRE_2011
