"""Structured audit logging helpers for NYC Taxi pipeline executions."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

# Standard pipeline logger instance
logger = logging.getLogger("nyc_taxi_data_platform")


def new_run_id() -> str:
    """Generate a unique UUID identifier for a pipeline run."""
    return str(uuid.uuid4())


@dataclass
class AuditEvent:
    """Structured audit log event representing stage execution status and metrics.

    Attributes:
        run_id: Unique pipeline run UUID.
        stage: Pipeline stage name (e.g. 'init_catalog', 'process_file').
        status: Execution outcome ('success', 'failed', 'running').
        message: Human-readable status description or error details.
        record_count: Number of records processed by the stage if applicable.
        duration_ms: Duration of stage execution in milliseconds.
        extra: Additional arbitrary context dictionary.
    """

    run_id: str
    stage: str
    status: str
    message: str
    record_count: int | None = None
    duration_ms: int | None = None
    extra: dict[str, Any] | None = None

    def to_json(self) -> str:
        """Serialize event to a JSON string including UTC timestamp."""
        payload = asdict(self)
        payload["logged_at"] = datetime.now(timezone.utc).isoformat()
        return json.dumps(payload, default=str)


def log_audit(event: AuditEvent) -> None:
    """Emit structured audit log event to standard logger output."""
    logger.info(event.to_json())
