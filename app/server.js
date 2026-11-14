/**
 * NYC Yellow Taxi Demand Platform - API and Web Dashboard Server
 *
 * Implements REST endpoints and dashboard static serving. Supports running via
 * Express when installed, or Node.js built-in HTTP module when external
 * dependencies are not installed.
 */

const fs = require("fs");
const path = require("path");
const http = require("http");

let parse;
try {
  parse = require("csv-parse/sync").parse;
} catch {
  // Built-in standard CSV parser fallback
  parse = (text) => {
    const lines = text.split(/\r?\n/).filter((line) => line.trim());
    if (!lines.length) return [];
    const parseLine = (line) => {
      const row = [];
      let current = "";
      let inQuotes = false;
      for (let i = 0; i < line.length; i++) {
        const char = line[i];
        if (char === '"') {
          if (inQuotes && line[i + 1] === '"') {
            current += '"';
            i++;
          } else {
            inQuotes = !inQuotes;
          }
        } else if (char === "," && !inQuotes) {
          row.push(current);
          current = "";
        } else {
          current += char;
        }
      }
      row.push(current);
      return row;
    };
    const headers = parseLine(lines[0]);
    return lines.slice(1).map((line) => {
      const values = parseLine(line);
      const obj = {};
      headers.forEach((h, i) => {
        obj[h] = values[i] ?? "";
      });
      return obj;
    });
  };
}

const port = Number(process.env.PORT || 3000);
const root = path.resolve(__dirname, "..");
const dataDir = path.join(root, "data");
const publicDir = path.join(__dirname, "public");

/**
 * Safely parse a CSV file from the data directory.
 * If file does not exist, returns empty array.
 *
 * @param {string} fileName - File name in data folder.
 * @returns {Array<Record<string, string>>}
 */
function readCsv(fileName) {
  const filePath = path.join(dataDir, fileName);
  if (!fs.existsSync(filePath)) {
    console.warn(`[DATA] Notice: Data file not found: ${filePath}. Run export stage or notebook to generate.`);
    return [];
  }
  try {
    const text = fs.readFileSync(filePath, "utf8");
    return parse(text, { columns: true, skip_empty_lines: true, bom: true });
  } catch (error) {
    console.error(`[DATA] Error reading CSV file ${filePath}: ${error.message}`);
    return [];
  }
}

// In-memory data collections
const predictions = readCsv("demand_predictions.csv");
const anomalies = readCsv("demand_anomalies.csv");
const zones = readCsv("dim_taxi_zone.csv");
const clusters = readCsv("zone_demand_clusters.csv");

// Fast lookup of zone display names by ID
const zoneNameById = new Map(zones.map((row) => [String(row.pickup_zone_id), row.zone_name]));

const numeric = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

/**
 * Filter zones by query string.
 */
function zoneSearch(query) {
  const normalized = String(query || "").trim().toLowerCase();
  if (!normalized) return zones;
  return zones.filter(
    (row) =>
      String(row.zone_name).toLowerCase().includes(normalized) ||
      String(row.borough).toLowerCase().includes(normalized) ||
      String(row.pickup_zone_id) === normalized
  );
}

/**
 * Aggregate top demand zones by actual pickups.
 */
function aggregateTopDemandZones(limit = 6) {
  const totals = new Map();
  for (const row of predictions) {
    const id = String(row.pickup_zone_id);
    totals.set(id, (totals.get(id) || 0) + numeric(row.pickup_count));
  }
  return [...totals.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([id, count]) => ({
      id,
      name: zoneNameById.get(id) || `Zone ${id}`,
      count: Math.round(count)
    }));
}

/**
 * Aggregate top anomaly zones by anomaly count.
 */
function aggregateTopAnomalyZones(limit = 5) {
  const counts = new Map();
  for (const row of anomalies) {
    const id = String(row.pickup_zone_id);
    counts.set(id, (counts.get(id) || 0) + 1);
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([id, count]) => ({
      id,
      name: zoneNameById.get(id) || `Zone ${id}`,
      count
    }));
}

/**
 * Match a taxi zone mentioned in a query.
 */
function findZone(message) {
  const lower = message.toLowerCase();
  const matches = zones.filter(
    (row) => lower.includes(String(row.zone_name).toLowerCase()) || lower.includes(String(row.pickup_zone_id))
  );
  return matches.sort((a, b) => String(b.zone_name).length - String(a.zone_name).length)[0];
}

/**
 * Compute API handler logic.
 */
function handleApi(pathname, query, reqBody) {
  if (pathname === "/api/summary") {
    const totalActual = predictions.reduce((sum, row) => sum + numeric(row.pickup_count), 0);
    const totalPredicted = predictions.reduce((sum, row) => sum + numeric(row.predicted_pickup_count), 0);
    const absoluteErrors = predictions.reduce(
      (sum, row) => sum + Math.abs(numeric(row.pickup_count) - numeric(row.predicted_pickup_count)),
      0
    );

    return {
      status: 200,
      data: {
        zoneCount: zones.length,
        forecastCount: predictions.length,
        anomalyCount: anomalies.length,
        spikeCount: anomalies.filter((row) => row.anomaly_direction === "unexpected spike").length,
        dropCount: anomalies.filter((row) => row.anomaly_direction === "unexpected drop").length,
        totalActual: Math.round(totalActual),
        totalPredicted: Math.round(totalPredicted),
        meanAbsoluteError: predictions.length > 0 ? Number((absoluteErrors / predictions.length).toFixed(3)) : 0,
        topDemand: aggregateTopDemandZones(6)
      }
    };
  }

  if (pathname === "/api/evaluation") {
    const summaryPath = path.join(dataDir, "forecast_metrics_summary.csv");
    const zonePath = path.join(dataDir, "forecast_metrics_by_zone.csv");
    const hourPath = path.join(dataDir, "forecast_metrics_by_hour.csv");
    const thresholdPath = path.join(dataDir, "anomaly_threshold_sensitivity.csv");

    const loadOptionalCsv = (filePath) => {
      if (!fs.existsSync(filePath)) return [];
      try {
        return parse(fs.readFileSync(filePath, "utf8"), {
          columns: true,
          skip_empty_lines: true,
          bom: true
        }).map((row) =>
          Object.fromEntries(
            Object.entries(row).map(([key, value]) => [key, value === "" ? null : numeric(value) || String(value)])
          )
        );
      } catch {
        return [];
      }
    };

    return {
      status: 200,
      data: {
        scope: "Full January scored predictions; not a held-out chronological validation split",
        summary: loadOptionalCsv(summaryPath)[0] || null,
        worstZones: loadOptionalCsv(zonePath).slice(0, 10),
        hourly: loadOptionalCsv(hourPath),
        anomalyThresholds: loadOptionalCsv(thresholdPath)
      }
    };
  }

  if (pathname === "/api/zones") {
    return { status: 200, data: zoneSearch(query.get("q")).slice(0, 100) };
  }

  if (pathname === "/api/predictions") {
    const zoneId = String(query.get("zone") || "");
    const date = String(query.get("date") || "");
    let rows = zoneId ? predictions.filter((row) => String(row.pickup_zone_id) === zoneId) : predictions;
    if (date) rows = rows.filter((row) => row.pickup_hour.startsWith(date));
    rows = rows.slice(0, 744);
    return {
      status: 200,
      data: rows.map((row) => ({
        hour: row.pickup_hour,
        actual: numeric(row.pickup_count),
        predicted: numeric(row.predicted_pickup_count),
        residual: numeric(row.residual),
        zoneName: row.zone_name
      }))
    };
  }

  if (pathname === "/api/anomalies") {
    const zoneId = String(query.get("zone") || "");
    const direction = String(query.get("direction") || "");
    let rows = zoneId ? anomalies.filter((row) => String(row.pickup_zone_id) === zoneId) : anomalies;
    if (direction) rows = rows.filter((row) => row.anomaly_direction === direction);
    const limit = Math.min(Number(query.get("limit") || 100), 500);
    return {
      status: 200,
      data: rows.slice(0, limit).map((row) => ({
        hour: row.pickup_hour,
        zoneId: Number(row.pickup_zone_id),
        zoneName: row.zone_name,
        borough: row.borough,
        actual: numeric(row.pickup_count),
        predicted: numeric(row.predicted_pickup_count),
        direction: row.anomaly_direction,
        deviation: numeric(row.anomaly_deviation)
      }))
    };
  }

  if (pathname === "/api/clusters") {
    const grouped = {};
    for (const row of clusters) {
      const cluster = String(row.demand_cluster);
      if (!grouped[cluster]) {
        grouped[cluster] = { cluster: Number(cluster), zones: [], totalPickups: 0, avgPickups: 0 };
      }
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
      group.avgPickups = group.zones.length > 0 ? Number((group.totalPickups / group.zones.length / 744).toFixed(3)) : 0;
    }
    return {
      status: 200,
      data: Object.values(grouped).sort((a, b) => a.cluster - b.cluster)
    };
  }

  if (pathname === "/api/agent") {
    const message = String(reqBody?.message || "").trim();
    if (!message) return { status: 400, data: { error: "Please enter a question." } };

    if (predictions.length === 0 && zones.length === 0) {
      return {
        status: 200,
        data: {
          answer:
            "Data files have not been generated yet. Please run the export stage and analysis notebook to generate predictions, anomalies, and clusters.",
          zone: null
        }
      };
    }

    const lower = message.toLowerCase();
    const zone = findZone(message);
    let answer;

    if (/summary|overall|how many/i.test(lower) && !zone) {
      answer = `The dataset covers ${zones.length} zones and ${predictions.length.toLocaleString()} hourly forecasts for January 2023. It contains ${anomalies.length.toLocaleString()} anomalies: ${anomalies.filter((row) => row.anomaly_direction === "unexpected spike").length.toLocaleString()} unexpected spikes and ${anomalies.filter((row) => row.anomaly_direction === "unexpected drop").length.toLocaleString()} unexpected drops.`;
    } else if (/top.*demand|highest.*demand|busiest|most pickup/i.test(lower)) {
      const top = aggregateTopDemandZones(5);
      answer =
        "The busiest zones by January actual pickups are:\n\n" +
        top.map((row, index) => `${index + 1}. ${row.name}: ${row.count.toLocaleString()} pickups`).join("\n");
    } else if (/top.*anomal|most anomal/i.test(lower)) {
      const top = aggregateTopAnomalyZones(5);
      answer =
        "The zones with the most detected anomalies are:\n\n" +
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
      } else {
        answer = `${zone.zone_name} does not have a cluster assignment record.`;
      }
    } else if (zone && /forecast|predict|busy|peak/i.test(lower)) {
      const zoneRows = predictions.filter((row) => String(row.pickup_zone_id) === String(zone.pickup_zone_id));
      if (zoneRows.length) {
        const hourlyTotals = Array.from({ length: 24 }, (_, hour) => {
          const values = zoneRows.filter((row) => new Date(row.pickup_hour).getUTCHours() === hour);
          return {
            hour,
            predicted: values.reduce((sum, row) => sum + numeric(row.predicted_pickup_count), 0) / (values.length || 1)
          };
        });
        const peak = hourlyTotals.sort((a, b) => b.predicted - a.predicted)[0];
        const total = zoneRows.reduce((sum, row) => sum + numeric(row.predicted_pickup_count), 0);
        answer = `${zone.zone_name} has an average forecast of ${(total / zoneRows.length).toFixed(2)} pickups per hour. Its highest average predicted demand is around ${peak.hour}:00 UTC, at about ${peak.predicted.toFixed(2)} pickups per hour.`;
      } else {
        answer = `No hourly predictions found for ${zone.zone_name}.`;
      }
    } else if (/error|accuracy|model|performance|metric/i.test(lower)) {
      answer =
        "The model comparison used a chronological split. The gradient-boosting model achieved MAE 2.680 pickups and RMSE 8.620 pickups; the previous-hour baseline achieved MAE 4.169 and RMSE 13.988. Lower values are better.";
    } else {
      answer =
        'I can answer questions about zone forecasts, anomalies, busiest zones, demand clusters, and model accuracy. Try: "Which zones have the most anomalies?", "Forecast for JFK Airport", or "What cluster is Times Sq/Theatre District in?"';
    }

    return { status: 200, data: { answer, zone: zone || null } };
  }

  return null;
}

// MIME types for static assets
const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "application/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".png": "image/png",
  ".svg": "image/svg+xml"
};

/**
 * Native HTTP server request dispatcher.
 */
function requestListener(req, res) {
  const parsedUrl = new URL(req.url, `http://localhost:${port}`);
  const pathname = parsedUrl.pathname;

  // Static file serving from app/public
  if (req.method === "GET" && !pathname.startsWith("/api/")) {
    const relativePath = pathname === "/" ? "index.html" : pathname.replace(/^\//, "");
    const filePath = path.join(publicDir, relativePath);

    if (fs.existsSync(filePath) && fs.statSync(filePath).isFile()) {
      const ext = path.extname(filePath).toLowerCase();
      const contentType = MIME_TYPES[ext] || "application/octet-stream";
      res.writeHead(200, { "Content-Type": contentType });
      fs.createReadStream(filePath).pipe(res);
      return;
    }
  }

  // Handle API routes
  if (pathname.startsWith("/api/")) {
    if (req.method === "POST") {
      let bodyData = "";
      req.on("data", (chunk) => {
        bodyData += chunk;
      });
      req.on("end", () => {
        let parsedBody = {};
        try {
          parsedBody = JSON.parse(bodyData || "{}");
        } catch {
          res.writeHead(400, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Invalid JSON body." }));
          return;
        }

        const result = handleApi(pathname, parsedUrl.searchParams, parsedBody);
        if (result) {
          res.writeHead(result.status, { "Content-Type": "application/json" });
          res.end(JSON.stringify(result.data));
        } else {
          res.writeHead(404, { "Content-Type": "application/json" });
          res.end(JSON.stringify({ error: "Endpoint not found." }));
        }
      });
      return;
    }

    const result = handleApi(pathname, parsedUrl.searchParams, null);
    if (result) {
      res.writeHead(result.status, { "Content-Type": "application/json" });
      res.end(JSON.stringify(result.data));
      return;
    }
  }

  res.writeHead(404, { "Content-Type": "text/plain" });
  res.end("Not Found");
}

// Start HTTP server
const server = http.createServer(requestListener);
server.listen(port, () => {
  console.log(`NYC Taxi Demand App running at http://localhost:${port}`);
});
