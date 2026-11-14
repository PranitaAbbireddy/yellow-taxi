# NYC Taxi Data Platform - Raw Data Upload Helper
# Uploads local TLC taxi zone reference CSV and trip Parquet files to Unity Catalog Volumes.
# Pre-requisite: Unity Catalog volume must already exist in Databricks.

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$Data = Join-Path $Root "data\raw"

# Create destination volume subdirectories in Databricks File System (DBFS)
databricks fs mkdir "dbfs:/Volumes/nyc_taxi/bronze/raw/reference" -p DEFAULT
databricks fs mkdir "dbfs:/Volumes/nyc_taxi/bronze/raw/yellow" -p DEFAULT

# Upload taxi zone lookup reference table
databricks fs cp (Join-Path $Data "reference\taxi_zone_lookup.csv") `
  "dbfs:/Volumes/nyc_taxi/bronze/raw/reference/taxi_zone_lookup.csv" -p DEFAULT --overwrite

# Upload January 2023 yellow taxi trip dataset
databricks fs cp (Join-Path $Data "yellow\yellow_tripdata_2023-01.parquet") `
  "dbfs:/Volumes/nyc_taxi/bronze/raw/yellow/yellow_tripdata_2023-01.parquet" -p DEFAULT --overwrite

Write-Host "Raw data upload to Unity Catalog Volume complete."
