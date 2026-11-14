"""Unity Catalog DDL definitions and idempotent schema/table management.

Contains idempotent CREATE statements for Catalog, Schemas, Volumes, and Delta Tables
across the Bronze, Silver, and Gold layers.
"""

from __future__ import annotations

from nyc_taxi_data_platform.config import PipelineConfig


def ensure_schemas_sql(config: PipelineConfig) -> list[str]:
    """Generate DDL statements to ensure the catalog, schemas, and volumes exist.

    Args:
        config: Current pipeline configuration.

    Returns:
        List of SQL CREATE IF NOT EXISTS statements.
    """
    cat = config.catalog
    return [
        f"CREATE CATALOG IF NOT EXISTS {cat}",
        f"CREATE SCHEMA IF NOT EXISTS {cat}.{config.bronze_schema}",
        f"CREATE SCHEMA IF NOT EXISTS {cat}.{config.silver_schema}",
        f"CREATE SCHEMA IF NOT EXISTS {cat}.{config.gold_schema}",
        f"CREATE VOLUME IF NOT EXISTS {cat}.{config.gold_schema}.exports",
    ]


# Bronze layer: raw ingested tables, ingestion tracking manifest, and audit logs
BRONZE_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS {catalog}.{bronze}.yellow_taxi_trips (
  source_file STRING NOT NULL,
  source_month STRING NOT NULL,
  ingestion_run_id STRING NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  vendor_id INT,
  tpep_pickup_datetime TIMESTAMP,
  tpep_dropoff_datetime TIMESTAMP,
  passenger_count INT,
  trip_distance DOUBLE,
  rate_code_id INT,
  store_and_fwd_flag STRING,
  pickup_location_id INT,
  dropoff_location_id INT,
  payment_type INT,
  fare_amount DOUBLE,
  extra DOUBLE,
  mta_tax DOUBLE,
  tip_amount DOUBLE,
  tolls_amount DOUBLE,
  improvement_surcharge DOUBLE,
  total_amount DOUBLE,
  congestion_surcharge DOUBLE,
  airport_fee DOUBLE,
  cbd_congestion_fee DOUBLE,
  raw_columns MAP<STRING, STRING>
) USING DELTA
PARTITIONED BY (source_month);

CREATE TABLE IF NOT EXISTS {catalog}.{bronze}.taxi_zone_lookup (
  location_id INT NOT NULL,
  borough STRING,
  zone STRING,
  service_zone STRING,
  source_file STRING,
  ingested_at TIMESTAMP
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.{bronze}.ingestion_manifest (
  source_file_identity STRING NOT NULL,
  source_file STRING NOT NULL,
  source_month STRING NOT NULL,
  ingestion_run_id STRING NOT NULL,
  ingested_at TIMESTAMP NOT NULL,
  record_count BIGINT,
  processing_status STRING NOT NULL,
  error_message STRING
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.{bronze}.pipeline_audit_log (
  run_id STRING NOT NULL,
  stage STRING NOT NULL,
  status STRING NOT NULL,
  message STRING,
  record_count BIGINT,
  duration_ms BIGINT,
  logged_at TIMESTAMP NOT NULL,
  extra STRING
) USING DELTA;
"""

# Silver layer: standardized trips, quarantined invalid rows, dimension zones, and DQ results
SILVER_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS {catalog}.{silver}.trips (
  trip_fingerprint STRING NOT NULL,
  source_file STRING NOT NULL,
  source_month STRING NOT NULL,
  ingestion_run_id STRING NOT NULL,
  vendor_id INT,
  pickup_datetime TIMESTAMP NOT NULL,
  dropoff_datetime TIMESTAMP,
  pickup_zone_id INT NOT NULL,
  dropoff_zone_id INT,
  trip_distance DOUBLE,
  fare_amount DOUBLE,
  passenger_count INT,
  payment_type INT,
  local_timezone STRING NOT NULL,
  processed_at TIMESTAMP NOT NULL
) USING DELTA
PARTITIONED BY (source_month);

CREATE TABLE IF NOT EXISTS {catalog}.{silver}.quarantined_trips (
  source_file STRING,
  source_month STRING,
  ingestion_run_id STRING,
  rejection_reason STRING NOT NULL,
  raw_payload STRING,
  processed_at TIMESTAMP NOT NULL
) USING DELTA
PARTITIONED BY (source_month);

CREATE TABLE IF NOT EXISTS {catalog}.{silver}.taxi_zones (
  zone_id INT NOT NULL,
  borough STRING,
  zone_name STRING,
  service_zone STRING,
  processed_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.{silver}.data_quality_results (
  run_id STRING NOT NULL,
  stage STRING NOT NULL,
  check_name STRING NOT NULL,
  status STRING NOT NULL,
  expected_value STRING,
  actual_value STRING,
  recorded_at TIMESTAMP NOT NULL
) USING DELTA;
"""

# Gold layer: business facts, dimensions, and ML feature tables
GOLD_TABLES_SQL = """
CREATE TABLE IF NOT EXISTS {catalog}.{gold}.fact_pickups_hourly (
  pickup_hour TIMESTAMP NOT NULL,
  pickup_zone_id INT NOT NULL,
  pickup_count BIGINT NOT NULL,
  processed_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.{gold}.dim_taxi_zone (
  pickup_zone_id INT NOT NULL,
  borough STRING,
  zone_name STRING,
  service_zone STRING,
  processed_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.{gold}.ml_training_features (
  pickup_zone_id INT NOT NULL,
  forecast_hour TIMESTAMP NOT NULL,
  hour_of_day INT NOT NULL,
  day_of_week INT NOT NULL,
  day_of_month INT NOT NULL,
  month INT NOT NULL,
  is_weekend BOOLEAN NOT NULL,
  lag_1h DOUBLE,
  lag_24h DOUBLE,
  lag_168h DOUBLE,
  rolling_mean_24h DOUBLE,
  rolling_mean_168h DOUBLE,
  rolling_std_24h DOUBLE,
  target_pickup_count BIGINT NOT NULL,
  processed_at TIMESTAMP NOT NULL
) USING DELTA;

CREATE TABLE IF NOT EXISTS {catalog}.{gold}.ml_inference_features (
  pickup_zone_id INT NOT NULL,
  forecast_hour TIMESTAMP NOT NULL,
  hour_of_day INT NOT NULL,
  day_of_week INT NOT NULL,
  day_of_month INT NOT NULL,
  month INT NOT NULL,
  is_weekend BOOLEAN NOT NULL,
  lag_1h DOUBLE,
  lag_24h DOUBLE,
  lag_168h DOUBLE,
  rolling_mean_24h DOUBLE,
  rolling_mean_168h DOUBLE,
  rolling_std_24h DOUBLE,
  processed_at TIMESTAMP NOT NULL
) USING DELTA;
"""


def all_ddl_statements(config: PipelineConfig) -> list[str]:
    """Assemble all schema and table DDL statements formatted with config parameters.

    Args:
        config: Current pipeline configuration.

    Returns:
        List of SQL execution strings in logical dependency order.
    """
    statements = ensure_schemas_sql(config)
    fmt = {
        "catalog": config.catalog,
        "bronze": config.bronze_schema,
        "silver": config.silver_schema,
        "gold": config.gold_schema,
    }
    for block in (BRONZE_TABLES_SQL, SILVER_TABLES_SQL, GOLD_TABLES_SQL):
        for stmt in block.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                statements.append(stmt.format(**fmt))
    return statements
