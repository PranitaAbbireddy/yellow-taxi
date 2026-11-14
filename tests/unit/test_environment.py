"""Unit tests for local environment preflight checks."""

from nyc_taxi_data_platform.environment.checks import run_local_checks


def test_local_checks_run():
    """Verify that run_local_checks executes and includes python_version check."""
    results = run_local_checks()
    names = {r.name for r in results}
    assert "python_version" in names
    assert all(r.name for r in results)
