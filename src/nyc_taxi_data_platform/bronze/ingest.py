"""Bronze ingestion helpers for file identity, month inference, and path resolution.

Provides deterministic file fingerprinting for ingestion deduplication and path
mapping across Unity Catalog volumes.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import PurePosixPath

# Regex pattern matching YYYY-MM inside file path strings
SOURCE_MONTH_PATTERN = re.compile(r"(\d{4})-(\d{2})")


def source_file_identity(source_path: str, file_size_bytes: int | None = None) -> str:
    """Generate a stable SHA-256 identity hash for deduplicating ingestion of the same file.

    Normalizes Windows/POSIX path separators to ensure consistent hashing across environments.

    Args:
        source_path: Input file path.
        file_size_bytes: Optional file size in bytes for stricter deduplication.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    normalized = PurePosixPath(source_path.replace("\\", "/")).as_posix()
    size_part = str(file_size_bytes) if file_size_bytes is not None else "unknown"
    payload = f"{normalized}|{size_part}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def infer_source_month(source_path: str, explicit: str | None = None) -> str:
    """Extract partition month (YYYY-MM) from file path or fallback to explicit value.

    Args:
        source_path: File path string to search for YYYY-MM pattern.
        explicit: Optional explicit month override.

    Returns:
        String representing month in YYYY-MM format.

    Raises:
        ValueError: If month pattern cannot be found and no explicit month was provided.
    """
    if explicit:
        return explicit
    match = SOURCE_MONTH_PATTERN.search(source_path)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    raise ValueError(f"Cannot infer source month from path: {source_path}")


def resolve_trip_paths(
    volume_base: str,
    source_months: list[str],
    source_files: list[str],
) -> list[str]:
    """Build normalized POSIX paths under volume_base for configured inputs.

    Args:
        volume_base: Base directory path in Unity Catalog volume.
        source_months: List of source months to generate standard parquet paths for.
        source_files: Explicit file paths to append.

    Returns:
        List of resolved full file paths.
    """
    paths: list[str] = []
    base = volume_base.rstrip("/")
    for month in source_months:
        paths.append(f"{base}/yellow/yellow_tripdata_{month}.parquet")
    paths.extend(source_files)
    return paths
