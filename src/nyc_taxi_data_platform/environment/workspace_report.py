"""Databricks workspace compatibility and Unity Catalog discovery report.

Executes Databricks CLI commands to verify catalog existence and list available catalogs
for deployment configuration.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import asdict, dataclass

from nyc_taxi_data_platform.config import load_config


@dataclass
class WorkspaceReport:
    """Workspace catalog status report.

    Attributes:
        catalog_exists: True if target catalog exists in workspace.
        catalog_name: Target catalog name tested.
        catalogs_listed: List of all catalogs discovered in the workspace.
        notes: Diagnostic and troubleshooting recommendations.
        cli_catalog_get_rc: Return code of the 'databricks catalogs get' command.
    """

    catalog_exists: bool
    catalog_name: str
    catalogs_listed: list[str]
    notes: list[str]
    cli_catalog_get_rc: int | None = None


def _run_databricks(args: list[str]) -> tuple[int, str]:
    """Execute databricks CLI subcommand and capture return code and combined output."""
    try:
        proc = subprocess.run(
            ["databricks", *args],
            capture_output=True,
            text=True,
            check=False,
        )
        output = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, output.strip()
    except FileNotFoundError:
        return 127, "databricks CLI not found on PATH"


def build_workspace_report(profile: str = "DEFAULT") -> WorkspaceReport:
    """Probe Databricks workspace using the CLI to check catalog accessibility.

    Args:
        profile: Databricks CLI authentication profile name.

    Returns:
        WorkspaceReport with findings and configuration advice.
    """
    config = load_config()
    notes: list[str] = []

    # List all catalogs
    rc, out = _run_databricks(["catalogs", "list", "-p", profile, "-o", "json"])
    catalogs: list[str] = []
    if rc == 0:
        try:
            data = json.loads(out)
            catalogs = [item.get("name", "") for item in data if isinstance(item, dict)]
        except json.JSONDecodeError:
            notes.append("Failed to parse catalogs list JSON from CLI.")
    else:
        notes.append(f"catalogs list failed (rc={rc}): {out[:500]}")

    # Test access to target catalog
    get_rc, get_out = _run_databricks(
        ["catalogs", "get", config.catalog, "-p", profile, "-o", "json"]
    )
    catalog_exists = get_rc == 0
    if not catalog_exists:
        notes.append(
            f"Catalog '{config.catalog}' not found. Create it in the workspace UI or "
            f"set NYC_TAXI_CATALOG to an existing catalog (e.g. workspace)."
        )
        notes.append(get_out[:300])

    return WorkspaceReport(
        catalog_exists=catalog_exists,
        catalog_name=config.catalog,
        catalogs_listed=catalogs,
        notes=notes,
        cli_catalog_get_rc=get_rc if get_rc != 127 else None,
    )


def main() -> int:
    """CLI entry point to output JSON workspace compatibility report."""
    profile = sys.argv[1] if len(sys.argv) > 1 else "DEFAULT"
    report = build_workspace_report(profile=profile)
    print(json.dumps(asdict(report), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
