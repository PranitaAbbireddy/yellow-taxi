"""Local runtime dependency and environment compatibility checks.

Verifies Python runtime version and critical module availability (yaml, pyarrow, pyspark).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CheckResult:
    """Individual check execution outcome.

    Attributes:
        name: Name of the check performed.
        passed: Boolean indicating whether check passed.
        detail: Human-readable diagnostic details.
    """

    name: str
    passed: bool
    detail: str


def check_python_version(min_minor: int = 10) -> CheckResult:
    """Check that the active Python interpreter meets the minimum version (Python 3.10+).

    Args:
        min_minor: Minimum required minor version for Python 3.

    Returns:
        CheckResult instance.
    """
    version = sys.version_info
    ok = version.major == 3 and version.minor >= min_minor
    return CheckResult(
        name="python_version",
        passed=ok,
        detail=f"{version.major}.{version.minor}.{version.micro}",
    )


def _import_check(module: str) -> CheckResult:
    """Attempt dynamic module import to verify package installation."""
    try:
        __import__(module)
        return CheckResult(name=f"import_{module}", passed=True, detail="ok")
    except ImportError as exc:
        return CheckResult(
            name=f"import_{module}",
            passed=False,
            detail=str(exc),
        )


def run_local_checks() -> list[CheckResult]:
    """Execute standard suite of local preflight environment checks.

    Returns:
        List of CheckResult outcomes.
    """
    checks: list[Callable[[], CheckResult]] = [
        check_python_version,
        lambda: _import_check("yaml"),
        lambda: _import_check("pyarrow"),
        lambda: _import_check("pyspark"),
    ]
    return [fn() for fn in checks]
