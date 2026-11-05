const express = require("express");
const fs = require("fs");
const path = require("path");
const { parse } = require("csv-parse/sync");

const app = express();
const port = Number(process.env.PORT || 3000);
const root = path.resolve(__dirname, "..");
const dataDir = path.join(root, "data");

app.use(express.json());
app.use(express.static(path.join(__dirname, "public")));

function readCsv(fileName) {
  const text = fs.readFileSync(path.join(dataDir, fileName), "utf8");
  return parse(text, { columns: true, skip_empty_lines: true, bom: true });
}

const predictions = readCsv("demand_predictions.csv");
const anomalies = readCsv("demand_anomalies.csv");
const zones = readCsv("dim_taxi_zone.csv");
const clusters = readCsv("zone_demand_clusters.csv");

const zoneNameById = new Map(zones.map((row) => [String(row.pickup_zone_id), row.zone_name]));
const numeric = (value) => Number(value || 0);

function zoneSearch(query) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) return zones;
  return zones.filter((row) =>
    String(row.zone_name).toLowerCase().includes(normalized) ||
    String(row.borough).toLowerCase().includes(normalized) ||
    String(row.pickup_zone_id) === normalized
  );
}

app.get("/api/summary", (_req, res) => {
  const totalActual = predictions.reduce((sum, row) => sum + numeric(row.pickup_count), 0);
  const totalPredicted = predictions.reduce((sum, row) => sum + numeric(row.predicted_pickup_count), 0);
  const absoluteErrors = predictions.reduce((sum, row) =>
    sum + Math.abs(numeric(row.pickup_count) - numeric(row.predicted_pickup_count)), 0);
  res.json({
    zoneCount: zones.length,
    forecastCount: predictions.length,
    anomalyCount: anomalies.length,
    spikeCount: anomalies.filter((row) => row.anomaly_direction === "unexpected spike").length,
    dropCount: anomalies.filter((row) => row.anomaly_direction === "unexpected drop").length,
    totalActual: Math.round(totalActual),
    totalPredicted: Math.round(totalPredicted),
    meanAbsoluteError: Number((absoluteErrors / predictions.length).toFixed(3))
  });
});

app.get("/api/evaluation", (_req, res) => {
  const summaryPath = path.join(dataDir, "forecast_metrics_summary.csv");
  const zonePath = path.join(dataDir, "forecast_metrics_by_zone.csv");
  const hourPath = path.join(dataDir, "forecast_metrics_by_hour.csv");
  const thresholdPath = path.join(dataDir, "anomaly_threshold_sensitivity.csv");

  const loadOptionalCsv = (filePath) => {
    if (!fs.existsSync(filePath)) return [];
    return parse(fs.readFileSync(filePath, "utf8"), {
      columns: true,
      skip_empty_lines: true,
      bom: true
    }).map((row) => Object.fromEntries(
      Object.entries(row).map(([key, value]) => [key, value === "" ? null : numeric(value) || String(value)])
    ));
  };

  res.json({
    scope: "Full January scored predictions; not a held-out chronological validation split",
    summary: loadOptionalCsv(summaryPath)[0] || null,
    worstZones: loadOptionalCsv(zonePath).slice(0, 10),
    hourly: loadOptionalCsv(hourPath),
    anomalyThresholds: loadOptionalCsv(thresholdPath)
  });
});

app.get("/api/zones", (req, res) => {
  res.json(zoneSearch(req.query.q).slice(0, 100));
});

app.get("/api/predictions", (req, res) => {
  const zoneId = String(req.query.zone || "");
  const date = String(req.query.date || "");
  let rows = zoneId ? predictions.filter((row) => String(row.pickup_zone_id) === zoneId) : predictions;
  if (date) rows = rows.filter((row) => row.pickup_hour.startsWith(date));
  rows = rows.slice(0, 744);
  res.json(rows.map((row) => ({
    hour: row.pickup_hour,
    actual: numeric(row.pickup_count),
    predicted: numeric(row.predicted_pickup_count),
    residual: numeric(row.residual),
    zoneName: row.zone_name
  })));
});

app.get("/api/anomalies", (req, res) => {
  const zoneId = String(req.query.zone || "");
  const direction = String(req.query.direction || "");
  let rows = zoneId ? anomalies.filter((row) => String(row.pickup_zone_id) === zoneId) : anomalies;
  if (direction) rows = rows.filter((row) => row.anomaly_direction === direction);
  const limit = Math.min(Number(req.query.limit || 100), 500);
  res.json(rows.slice(0, limit).map((row) => ({
    hour: row.pickup_hour,
    zoneId: Number(row.pickup_zone_id),
    zoneName: row.zone_name,
    borough: row.borough,
    actual: numeric(row.pickup_count),
    predicted: numeric(row.predicted_pickup_count),
    direction: row.anomaly_direction,
    deviation: numeric(row.anomaly_deviation)
  })));
});

app.get("/api/clusters", (_req, res) => {
  const grouped = {};
  for (const row of clusters) {
    const cluster = String(row.demand_cluster);
    if (!grouped[cluster]) grouped[cluster] = { cluster: Number(cluster), zones: [], totalPickups: 0, avgPickups: 0 };
    grouped[cluster].zones.push({
      zoneId: Number(row.pickup_zone_id),
      zoneName: row.zone_name,
      borough: row.borough,
      avgPickups: numeric(row.avg_pickups),
      stdPickups: numeric(row.std_pickups),
      totalPickups: numeric(row.total_pickups)
    });
    grouped[cluster].totalPickups += numeric(row.total_pickups);
  }
  for (const group of Object.values(grouped)) {
    group.avgPickups = Number((group.totalPickups / group.zones.length / 744).toFixed(3));
  }
  res.json(Object.values(grouped).sort((a, b) => a.cluster - b.cluster));
});

function findZone(message) {
  const lower = message.toLowerCase();
  const matches = zones.filter((row) =>
    lower.includes(String(row.zone_name).toLowerCase()) ||
    lower.includes(String(row.pickup_zone_id))
  );
  return matches.sort((a, b) => String(b.zone_name).length - String(a.zone_name).length)[0];
}

function aggregateTopAnomalyZones(limit = 5) {
  const counts = new Map();
  for (const row of anomalies) {
    const id = String(row.pickup_zone_id);
    counts.set(id, (counts.get(id) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([id, count]) => ({ id, name: zoneNameById.get(id), count }));
}

function aggregateTopDemandZones(limit = 5) {
  const totals = new Map();
  for (const row of predictions) {
    const id = String(row.pickup_zone_id);
    totals.set(id, (totals.get(id) || 0) + numeric(row.pickup_count));
  }
  return [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([id, count]) => ({ id, name: zoneNameById.get(id), count: Math.round(count) }));
}

app.post("/api/agent", (req, res) => {
  const message = String(req.body.message || "").trim();
  if (!message) return res.status(400).json({ error: "Please enter a question." });

  const lower = message.toLowerCase();
  const zone = findZone(message);
  let answer;

  if (/summary|overall|how many/i.test(lower) && !zone) {
    answer = `The dataset covers ${zones.length} zones and ${predictions.length.toLocaleString()} hourly forecasts for January 2023. It contains ${anomalies.length.toLocaleString()} anomalies: ${anomalies.filter((row) => row.anomaly_direction === "unexpected spike").length.toLocaleString()} unexpected spikes and ${anomalies.filter((row) => row.anomaly_direction === "unexpected drop").length.toLocaleString()} unexpected drops.`;
  } else if (/top.*demand|highest.*demand|busiest|most pickup/i.test(lower)) {
    const top = aggregateTopDemandZones(5);
    answer = "The busiest zones by January actual pickups are:\n\n" +
      top.map((row, index) => `${index + 1}. ${row.name}: ${row.count.toLocaleString()} pickups`).join("\n");
  } else if (/top.*anomal|most anomal/i.test(lower)) {
    const top = aggregateTopAnomalyZones(5);
    answer = "The zones with the most detected anomalies are:\n\n" +
      top.map((row, index) => `${index + 1}. ${row.name}: ${row.count.toLocaleString()} anomalous hours`).join("\n");
  } else if (zone && /anomal/i.test(lower)) {
    const zoneRows = anomalies.filter((row) => String(row.pickup_zone_id) === String(zone.pickup_zone_id));
    const spikes = zoneRows.filter((row) => row.anomaly_direction === "unexpected spike").length;
    const drops = zoneRows.filter((row) => row.anomaly_direction === "unexpected drop").length;
    answer = `${zone.zone_name} has ${zoneRows.length.toLocaleString()} anomalous hours: ${spikes.toLocaleString()} spikes and ${drops.toLocaleString()} drops. An anomaly means actual demand differed sharply from the zone-hour forecast, not that an event is proven.`;
  } else if (zone && /cluster|profile|segment/i.test(lower)) {
    const cluster = clusters.find((row) => String(row.pickup_zone_id) === String(zone.pickup_zone_id));
    if (cluster) {
      answer = `${zone.zone_name} is assigned to K-Means cluster ${cluster.demand_cluster}. Its January average is ${numeric(cluster.avg_pickups).toFixed(2)} pickups per hour, with ${Math.round(numeric(cluster.total_pickups)).toLocaleString()} total pickups. Cluster IDs are profile labels, not rankings.`;
    }
  } else if (zone && /forecast|predict|busy|peak/i.test(lower)) {
    const zoneRows = predictions.filter((row) => String(row.pickup_zone_id) === String(zone.pickup_zone_id));
    if (zoneRows.length) {
      const hourlyTotals = Array.from({ length: 24 }, (_, hour) => {
        const values = zoneRows.filter((row) => new Date(row.pickup_hour).getUTCHours() === hour);
        return {
          hour,
          predicted: values.reduce((sum, row) => sum + numeric(row.predicted_pickup_count), 0) / values.length
        };
      });
      const peak = hourlyTotals.sort((a, b) => b.predicted - a.predicted)[0];
      const total = zoneRows.reduce((sum, row) => sum + numeric(row.predicted_pickup_count), 0);
      answer = `${zone.zone_name} has an average forecast of ${(total / zoneRows.length).toFixed(2)} pickups per hour. Its highest average predicted demand is around ${peak.hour}:00 UTC, at about ${peak.predicted.toFixed(2)} pickups per hour.`;
    }
  } else if (/error|accuracy|model|performance|metric/i.test(lower)) {
    answer = "The model comparison used a chronological split. The gradient-boosting model achieved MAE 2.680 pickups and RMSE 8.620 pickups; the previous-hour baseline achieved MAE 4.169 and RMSE 13.988. Lower values are better.";
  } else {
    answer = `I can answer questions about zone forecasts, anomalies, busiest zones, demand clusters, and model accuracy. Try: "Which zones have the most anomalies?", "Forecast for JFK Airport", or "What cluster is Times Sq/Theatre District in?"`;
  }

  res.json({ answer, zone: zone || null });
});

app.listen(port, () => {
  console.log(`NYC Taxi Demand App running at http://localhost:${port}`);
});
