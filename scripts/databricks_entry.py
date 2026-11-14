"""Databricks workflow entry point: resolves bundle src/ and executes pipeline stages.

Databricks asset bundles stage repository files under workspace paths. When executing
via Python tasks without an active __file__ context, this entry script walks parent
directories to locate and append 'src' to sys.path before invoking the stage runner.
"""

import sys
from pathlib import Path


def _bundle_src_path() -> Path:
    """Resolve the src/ directory containing the nyc_taxi_data_platform package."""
    cwd = Path.cwd()
    candidates = [
        cwd / "src",
        cwd / "files" / "src",
        cwd.parent / "src",
    ]
    for parent in [cwd, *cwd.parents]:
        candidates.append(parent / "src")
        candidates.append(parent / "files" / "src")
    for path in candidates:
        if (path / "nyc_taxi_data_platform").is_dir():
            return path.resolve()
    raise RuntimeError(
        f"Could not find nyc_taxi_data_platform under src/. Checked candidates from cwd={cwd}"
    )


# Ensure package path is registered at the head of sys.path
_SRC = _bundle_src_path()
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from nyc_taxi_data_platform.pipeline.stages import main

if __name__ == "__main__":
    main()
