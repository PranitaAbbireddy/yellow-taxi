"""Orchestrated pipeline stages (callable from jobs or tests)."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone

from pyspark.sql import SparkSession
from pyspark.sql import functions as F

from nyc_taxi_data_platform.bronze.ingest import source_file_identity
from nyc_taxi_data_platform.bronze.manifest import (
    ManifestRecord,
    apply_duplicate_policy,
    manifest_to_spark_df,
)
from nyc_taxi_data_platform.bronze.pipeline import read_parquet_with_validation
from nyc_taxi_data_platform.catalog.ddl import all_ddl_statements
from nyc_taxi_data_platform.config import load_config
from nyc_taxi_data_platform.gold.aggregates import hourly_pickups_from_silver, reconcile_counts
from nyc_taxi_data_platform.gold.coverage import apply_zero_fill, build_hourly_grid
from nyc_taxi_data_platform.gold.features import build_ml_features, to_inference_features
from nyc_taxi_data_platform.logging import AuditEvent, log_audit, new_run_id
from nyc_taxi_data_platform.silver.transform import (
    deduplicate_trips,
    split_valid_and_quarantine,
    standardize_bronze_trips,
)
from nyc_taxi_data_platform.pipeline.exports import stage_export_gold_csv
from nyc_taxi_data_platform.pipeline.writes import (
    append_bronze_trips,
    merge_gold_hourly,
    merge_manifest,
    overwrite_silver_partition,
)
from nyc_taxi_data_platform.silver.zones import standardize_zone_lookup


def get_spark(app_name: str = "nyc_taxi_data_platform") -> SparkSession:
    return SparkSession.builder.appName(app_name).getOrCreate()


def stage_init_catalog(spark: SparkSession) -> None:
    config = load_config()
    for stmt in all_ddl_statements(config):
        spark.sql(stmt)


def stage_silver_from_dataframe(spark: SparkSession, bronze_df) -> tuple:
    config = load_config()
    standardized = standardize_bronze_trips(bronze_df, config.local_timezone)
    valid, quarantined = split_valid_and_quarantine(standardized, config.quality)
    valid = deduplicate_trips(valid)
    return valid, quarantined


def stage_gold_hourly(spark: SparkSession, silver_trips) -> dict:
    config = load_config()
    hourly = hourly_pickups_from_silver(silver_trips)
    if config.coverage_start_date and config.coverage_end_date:
        zone_ids = [
            row.zone_id
            for row in spark.table(
                f"{config.catalog}.{config.silver_schema}.taxi_zones"
            ).select("zone_id").distinct().collect()
        ] if spark.catalog.tableExists(
            f"{config.catalog}.{config.silver_schema}.taxi_zones"
        ) else sorted(
            {r.pickup_zone_id for r in silver_trips.select("pickup_zone_id").distinct().collect()}
        )
        grid = build_hourly_grid(
            spark,
            zone_ids,
            f"{config.coverage_start_date} 00:00:00",
            f"{config.coverage_end_date} 23:00:00",
        )
        hourly = apply_zero_fill(hourly, grid)
    return {"hourly": hourly, "reconciliation": reconcile_counts(silver_trips, hourly)}


def stage_ml_features(hourly_df):
    training = build_ml_features(hourly_df)
    inference = to_inference_features(training)
    return training, inference


def _finalize_silver_gold(spark: SparkSession, bronze_df, source_month: str, run_id: str) -> None:
    config = load_config()
    valid, quarantined = stage_silver_from_dataframe(spark, bronze_df)
    overwrite_silver_partition(spark, valid, source_month)
    quarantine_table = f"{config.catalog}.{config.silver_schema}.quarantined_trips"
    spark.sql(f"DELETE FROM {quarantine_table} WHERE source_month = '{source_month}'")
    quarantined.write.format("delta").mode("append").saveAsTable(quarantine_table)
    gold = stage_gold_hourly(spark, valid)
    merge_gold_hourly(spark, gold["hourly"])
    training, inference = stage_ml_features(gold["hourly"])
    training.write.format("delta").mode("overwrite").saveAsTable(
        f"{config.catalog}.{config.gold_schema}.ml_training_features"
    )
    inference.write.format("delta").mode("overwrite").saveAsTable(
        f"{config.catalog}.{config.gold_schema}.ml_inference_features"
    )
    recon = gold["reconciliation"]
    dq_status = (
        "pass" if recon["silver_trip_count"] == recon["gold_pickup_sum"] else "fail"
    )
    spark.createDataFrame(
        [
            (
                run_id,
                "gold",
                "silver_gold_pickup_sum",
                dq_status,
                str(recon["silver_trip_count"]),
                str(recon["gold_pickup_sum"]),
            )
        ],
        [
            "run_id",
            "stage",
            "check_name",
            "status",
            "expected_value",
            "actual_value",
        ],
    ).withColumn("recorded_at", F.current_timestamp()).write.format("delta").mode(
        "append"
    ).saveAsTable(f"{config.catalog}.{config.silver_schema}.data_quality_results")
    log_audit(
        AuditEvent(
            run_id=run_id,
            stage="silver_gold",
            status="success",
            message=f"silver={recon['silver_trip_count']} gold_sum={recon['gold_pickup_sum']}",
            record_count=recon["silver_trip_count"],
        )
    )


def stage_ingest_zones(spark: SparkSession, lookup_path: str) -> None:
    config = load_config()
    raw = spark.read.option("header", True).csv(lookup_path)
    silver_zones = standardize_zone_lookup(raw)
    silver_zones.write.format("delta").mode("overwrite").saveAsTable(
        f"{config.catalog}.{config.silver_schema}.taxi_zones"
    )
    dim = silver_zones.select(
        F.col("zone_id").alias("pickup_zone_id"),
        F.col("borough"),
        F.col("zone_name"),
        F.col("service_zone"),
        F.col("processed_at"),
    )
    dim.write.format("delta").mode("overwrite").saveAsTable(
        f"{config.catalog}.{config.gold_schema}.dim_taxi_zone"
    )
    bronze_lookup = raw.select(
        F.col("LocationID").cast("int").alias("location_id"),
        F.col("Borough").alias("borough"),
        F.col("Zone").alias("zone"),
        F.col("service_zone"),
        F.lit(lookup_path).alias("source_file"),
        F.current_timestamp().alias("ingested_at"),
    )
    bronze_lookup.write.format("delta").mode("overwrite").saveAsTable(
        f"{config.catalog}.{config.bronze_schema}.taxi_zone_lookup"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="NYC Taxi pipeline stage runner")
    parser.add_argument(
        "--stage",
        required=True,
        choices=[
            "init_catalog",
            "audit_ping",
            "ingest_zones",
            "process_file",
            "backfill_silver_gold",
            "export_gold_csv",
        ],
    )
    parser.add_argument("--source-path", default="", help="Path for ingest_zones or process_file")
    parser.add_argument(
        "--source-month",
        default="",
        help="YYYY-MM for backfill_silver_gold from bronze table",
    )
    parser.add_argument(
        "--export-path",
        default="",
        help="Destination directory for export_gold_csv (defaults to the gold exports volume)",
    )
    args = parser.parse_args()
    run_id = new_run_id()
    spark = get_spark()
    start = datetime.now(timezone.utc)

    if args.stage == "init_catalog":
        stage_init_catalog(spark)
        log_audit(
            AuditEvent(
                run_id=run_id,
                stage="init_catalog",
                status="success",
                message="DDL applied",
                duration_ms=int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            )
        )
    elif args.stage == "ingest_zones":
        zone_path = args.source_path or "/Volumes/nyc_taxi/bronze/raw/reference/taxi_zone_lookup.csv"
        stage_init_catalog(spark)
        stage_ingest_zones(spark, zone_path)
        log_audit(
            AuditEvent(
                run_id=run_id,
                stage="ingest_zones",
                status="success",
                message=f"zones loaded from {zone_path}",
            )
        )
    elif args.stage == "audit_ping":
        log_audit(
            AuditEvent(
                run_id=run_id,
                stage="audit_ping",
                status="success",
                message="audit channel ok",
            )
        )
    elif args.stage == "process_file":
        if not args.source_path:
            raise SystemExit("--source-path is required for process_file")
        stage_init_catalog(spark)
        config = load_config()
        bronze_df, fields = read_parquet_with_validation(spark, args.source_path)
        identity = fields.get("source_file_identity") or source_file_identity(
            args.source_path, None
        )
        manifest = ManifestRecord(
            source_file_identity=identity,
            source_file=args.source_path,
            source_month=fields.get("source_month", "unknown"),
            ingestion_run_id=run_id,
            ingested_at=datetime.now(timezone.utc),
            record_count=int(fields.get("record_count", 0)),
            processing_status=fields.get("processing_status", "failed"),
            error_message=fields.get("error_message"),
        )
        known: set[str] = set()
        manifest_table = f"{config.catalog}.{config.bronze_schema}.ingestion_manifest"
        if spark.catalog.tableExists(manifest_table):
            known = {
                r.source_file_identity
                for r in spark.table(manifest_table).select("source_file_identity").distinct().collect()
            }
        manifest = apply_duplicate_policy(manifest, known)
        merge_manifest(spark, manifest_to_spark_df(spark, manifest))
        if bronze_df is None or manifest.processing_status != "ingested":
            log_audit(
                AuditEvent(
                    run_id=run_id,
                    stage="process_file",
                    status="failed",
                    message=manifest.error_message or manifest.processing_status,
                )
            )
            return
        append_bronze_trips(spark, bronze_df)
        _finalize_silver_gold(spark, bronze_df, manifest.source_month, run_id)
        log_audit(
            AuditEvent(
                run_id=run_id,
                stage="process_file",
                status="success",
                message="ingest and transform complete",
                record_count=manifest.record_count,
                duration_ms=int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            )
        )
    elif args.stage == "backfill_silver_gold":
        month = args.source_month or "2023-01"
        config = load_config()
        bronze_table = f"{config.catalog}.{config.bronze_schema}.yellow_taxi_trips"
        bronze_df = spark.table(bronze_table).filter(F.col("source_month") == month)
        if bronze_df.limit(1).count() == 0:
            raise SystemExit(f"No bronze rows for source_month={month}")
        _finalize_silver_gold(spark, bronze_df, month, run_id)
    elif args.stage == "export_gold_csv":
        config = load_config()
        results = stage_export_gold_csv(spark, config, args.export_path or None)
        log_audit(
            AuditEvent(
                run_id=run_id,
                stage="export_gold_csv",
                status="success",
                message=f"exported tables={sorted(results)} rows={sum(results.values())}",
                record_count=sum(results.values()),
                duration_ms=int((datetime.now(timezone.utc) - start).total_seconds() * 1000),
            )
        )


if __name__ == "__main__":
    main()
