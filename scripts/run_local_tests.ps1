# NYC Taxi Data Platform - Local Unit Test Runner
# Verifies virtual environment existence, installs dev package dependencies, and runs pytest.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot\..

# Ensure local virtual environment is initialized
if (-not (Test-Path ".venv")) {
    Write-Host "Creating Python virtual environment (.venv)..."
    python -m venv .venv
}

# Activate virtual environment
& .\.venv\Scripts\Activate.ps1

# Install package in editable mode with development dependencies
Write-Host "Installing package in editable mode with dev dependencies..."
pip install -e ".[dev]"

# Execute pytest on unit tests suite
Write-Host "Running unit test suite..."
pytest tests/unit -q
