const fs = require("fs");
const path = require("path");
const { parse } = require("csv-parse/sync");

const root = path.resolve(__dirname, "..");
const dataDir = path.join(root, "data");
const outputDir = path.join(dataDir);

function readCsv(fileName) {
  return parse(fs.readFileSync(path.join(dataDir, fileName), "utf8"), {
    columns: true,
    skip_empty_lines: true,
    bom: true
  });
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function round(value, digits = 3) {
  const factor = 10 ** digits;
  return Math.round((value + Number.EPSILON) * factor) / factor;
}

function median(values) {
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 === 0
    ? (sorted[middle - 1] + sorted[middle]) / 2
    : sorted[middle];
}

function regressionMetrics(rows) {
  const pairs = rows
    .map((row) => ({
      actual: number(row.pickup_count),
      predicted: number(row.predicted_pickup_count)
    }))
    .filter((row) => Number.isFinite(row.actual) && Number.isFinite(row.predicted));

  const actualMean = pairs.reduce((sum, row) => sum + row.actual, 0) / pairs.length;
  const absoluteErrors = pairs.map((row) => Math.abs(row.actual - row.predicted));
  const squaredErrors = pairs.map((row) => (row.actual - row.predicted) ** 2);
  const mae = absoluteErrors.reduce((sum, value) => sum + value, 0) / pairs.length;
  const rmse = Math.sqrt(squaredErrors.reduce((sum, value) => sum + value, 0) / pairs.length);
  const residualSumSquares = squaredErrors.reduce((sum, value) => sum + value, 0);
  const totalSumSquares = pairs.reduce((sum, row) => sum + (row.actual - actualMean) ** 2, 0);
  const r2 = totalSumSquares === 0 ? null : 1 - residualSumSquares / totalSumSquares;

  const mapeRows = pairs.filter((row) => row.actual !== 0);
  const mape = mapeRows.length
    ? mapeRows.reduce((sum, row) => sum + Math.abs(row.actual - row.predicted) / row.actual, 0) / mapeRows.length * 100
    : null;
  const smapeRows = pairs.filter((row) => row.actual + row.predicted !== 0);
  const smape = smapeRows.length
    ? smapeRows.reduce((sum, row) =>
      sum + 200 * Math.abs(row.actual - row.predicted) / (Math.abs(row.actual) + Math.abs(row.predicted)), 0) / smapeRows.length
    : null;
  const actualTotal = pairs.reduce((sum, row) => sum + row.actual, 0);
  const wape = actualTotal === 0 ? null : mae / (actualTotal / pairs.length) * 100;

  const sortedAbsoluteErrors = [...absoluteErrors].sort((a, b) => a - b);
  const medianAbsoluteError = sortedAbsoluteErrors[Math.floor(sortedAbsoluteErrors.length / 2)];
  const p95AbsoluteError = sortedAbsoluteErrors[Math.floor(sortedAbsoluteErrors.length * 0.95)];

  return {
    rows: pairs.length,
    mae: round(mae),
    rmse: round(rmse),
    r2: r2 === null ? null : round(r2),
    mape_percent: mape === null ? null : round(mape),
    smape_percent: smape === null ? null : round(smape),
    wape_percent: wape === null ? null : round(wape),
    demand_weighted_accuracy_percent: wape === null ? null : round(100 - wape),
    median_absolute_error: round(medianAbsoluteError),
    p95_absolute_error: round(p95AbsoluteError),
    within_1_pickup_percent: round(pairs.filter((row, index) => absoluteErrors[index] <= 1).length / pairs.length * 100),
    within_5_pickups_percent: round(pairs.filter((row, index) => absoluteErrors[index] <= 5).length / pairs.length * 100)
  };
}

function csvEscape(value) {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function writeCsv(fileName, rows) {
  if (!rows.length) return;
  const headers = Object.keys(rows[0]);
  const lines = [
    headers.join(","),
    ...rows.map((row) => headers.map((header) => csvEscape(row[header])).join(","))
  ];
  fs.writeFileSync(path.join(outputDir, fileName), lines.join("\n") + "\n", "utf8");
}

const predictions = readCsv("demand_predictions.csv");
const zones = readCsv("dim_taxi_zone.csv");
const overall = regressionMetrics(predictions);
writeCsv("forecast_metrics_summary.csv", [{ scope: "all_scored_zone_hours", ...overall }]);

const zoneNameById = new Map(zones.map((row) => [row.pickup_zone_id, row.zone_name]));
const zoneGroups = new Map();
for (const row of predictions) {
  if (!zoneGroups.has(row.pickup_zone_id)) zoneGroups.set(row.pickup_zone_id, []);
  zoneGroups.get(row.pickup_zone_id).push(row);
}

const zoneMetrics = [...zoneGroups.entries()].map(([zoneId, rows]) => ({
  pickup_zone_id: Number(zoneId),
  zone_name: zoneNameById.get(zoneId) || "",
  ...regressionMetrics(rows)
}));
writeCsv("forecast_metrics_by_zone.csv", zoneMetrics.sort((a, b) => b.mae - a.mae));

const hourGroups = new Map();
for (const row of predictions) {
  const hour = new Date(row.pickup_hour).getUTCHours();
  if (!hourGroups.has(hour)) hourGroups.set(hour, []);
  hourGroups.get(hour).push(row);
}
const hourlyMetrics = [...hourGroups.entries()].sort((a, b) => a[0] - b[0]).map(([hour, rows]) => ({
  hour_of_day: hour,
  ...regressionMetrics(rows)
}));
writeCsv("forecast_metrics_by_hour.csv", hourlyMetrics);

const residualsByZone = new Map();
for (const row of predictions) {
  const residual = number(row.residual);
  if (!residualsByZone.has(row.pickup_zone_id)) residualsByZone.set(row.pickup_zone_id, []);
  residualsByZone.get(row.pickup_zone_id).push(residual);
}

const thresholdRows = [];
for (const threshold of [2, 2.5, 3, 3.5, 4]) {
  let anomalies = 0;
  let spikes = 0;
  let drops = 0;
  for (const [zoneId, residuals] of residualsByZone.entries()) {
    const residualMedian = median(residuals);
    const mad = median(residuals.map((value) => Math.abs(value - residualMedian))) * 1.4826;
    for (let index = 0; index < residuals.length; index++) {
      const deviation = mad < 0.1
        ? Math.abs(residuals[index] - residualMedian) / 0.1
        : Math.abs(residuals[index] - residualMedian) / mad;
      if (deviation >= threshold) {
        anomalies++;
        if (residuals[index] >= 0) spikes++;
        else drops++;
      }
    }
  }
  thresholdRows.push({
    scaled_mad_threshold: threshold,
    anomaly_count: anomalies,
    anomaly_rate_percent: round(anomalies / predictions.length * 100),
    unexpected_spike_count: spikes,
    unexpected_drop_count: drops
  });
}
writeCsv("anomaly_threshold_sensitivity.csv", thresholdRows);

console.log(JSON.stringify({
  overall,
  outputs: [
    "forecast_metrics_summary.csv",
    "forecast_metrics_by_zone.csv",
    "forecast_metrics_by_hour.csv",
    "anomaly_threshold_sensitivity.csv"
  ]
}, null, 2));
