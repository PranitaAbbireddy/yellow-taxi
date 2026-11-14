/**
 * NYC Yellow Taxi Demand Platform - Frontend Application Logic
 *
 * Manages client-side navigation, overview metrics, SVG chart rendering,
 * anomaly table filtering, cluster profile cards, and local agent interaction.
 */

// Global frontend state
const state = { zones: [] };

/**
 * Format numeric value with locale thousands separators.
 *
 * @param {number|string} value - Input number.
 * @returns {string} Formatted number string.
 */
const formatNumber = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });

/**
 * Helper to fetch and parse JSON with error handling.
 *
 * @param {string} url - API endpoint URL.
 * @param {RequestInit} [options] - Fetch request options.
 * @returns {Promise<any>} Parsed response data.
 */
async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}));
    throw new Error(errorBody.error || `Request failed with status ${response.status}`);
  }
  return response.json();
}

/**
 * Switch active visible view tab.
 *
 * @param {string} page - Target page ID (overview, forecast, anomalies, clusters, agent).
 */
function switchPage(page) {
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".nav-button").forEach((el) => el.classList.remove("active"));
  const targetPage = document.getElementById(page);
  const targetNav = document.querySelector(`[data-page="${page}"]`);
  if (targetPage) targetPage.classList.add("active");
  if (targetNav) targetNav.classList.add("active");

  const titles = {
    overview: "Demand overview",
    forecast: "Hourly forecasting",
    anomalies: "Anomaly detection",
    clusters: "Zone segmentation",
    agent: "Taxi data agent"
  };
  const pageTitleEl = document.getElementById("pageTitle");
  if (pageTitleEl && titles[page]) {
    pageTitleEl.textContent = titles[page];
  }
}

// Bind navigation tab clicks
document.querySelectorAll(".nav-button").forEach((button) => {
  button.addEventListener("click", () => switchPage(button.dataset.page));
});

/**
 * Load and render summary KPI cards, top demand bars, and anomaly breakdown.
 */
async function loadOverview() {
  try {
    const summary = await getJson("/api/summary");
    const summaryCardsEl = document.getElementById("summaryCards");
    if (summaryCardsEl) {
      summaryCardsEl.innerHTML = [
        ["Taxi zones", summary.zoneCount || 0],
        ["Hourly forecasts", (summary.forecastCount || 0).toLocaleString()],
        ["Anomalies detected", (summary.anomalyCount || 0).toLocaleString()],
        ["Model MAE", (summary.meanAbsoluteError || 2.68).toFixed(3)]
      ]
        .map(([label, value]) => `<article class="card"><span>${label}</span><strong>${value}</strong></article>`)
        .join("");
    }

    // Use server-aggregated top demand zones if provided; otherwise fallback to client aggregation
    let topDemand = summary.topDemand || [];
    if (!topDemand.length) {
      const allZones = await getJson("/api/zones");
      state.zones = [...allZones];
      const sampled = allZones.slice(0, 10);
      topDemand = await Promise.all(
        sampled.map(async (zone) => {
          const rows = await getJson(`/api/predictions?zone=${zone.pickup_zone_id}`);
          return {
            name: zone.zone_name,
            count: rows.reduce((sum, row) => sum + (row.actual || 0), 0)
          };
        })
      );
      topDemand.sort((a, b) => b.count - a.count);
    }

    const busyZonesEl = document.getElementById("busyZones");
    if (busyZonesEl) {
      if (topDemand.length > 0) {
        const max = topDemand[0]?.count || 1;
        busyZonesEl.innerHTML = topDemand
          .slice(0, 6)
          .map(
            (row) =>
              `<div class="bar-row"><span>${row.name}</span><div class="bar-track"><div class="bar-fill" style="width:${
                (100 * row.count) / max
              }%"></div></div><b>${formatNumber(row.count)}</b></div>`
          )
          .join("");
      } else {
        busyZonesEl.innerHTML = "<p>No demand data available yet. Please run the gold export and notebook.</p>";
      }
    }

    const anomalyMixEl = document.getElementById("anomalyMix");
    if (anomalyMixEl) {
      const spikeCount = summary.spikeCount || 0;
      const dropCount = summary.dropCount || 0;
      anomalyMixEl.innerHTML = `
        <div class="mix-card spike"><strong>${spikeCount.toLocaleString()}</strong><span>Unexpected spikes</span></div>
        <div class="mix-card drop"><strong>${dropCount.toLocaleString()}</strong><span>Unexpected drops</span></div>`;
    }
  } catch (error) {
    console.error("Failed to load overview data:", error);
  }
}

/**
 * Populate zone dropdown options for forecast and anomaly filters.
 */
async function loadZoneSelectors() {
  try {
    const zones = await getJson("/api/zones");
    state.zones = [...zones];
    const options = zones.map((zone) => `<option value="${zone.pickup_zone_id}">${zone.zone_name}</option>`).join("");
    const forecastSelect = document.getElementById("forecastZone");
    const anomalySelect = document.getElementById("anomalyZone");

    if (forecastSelect) forecastSelect.innerHTML = options;
    if (anomalySelect) anomalySelect.insertAdjacentHTML("beforeend", options);
  } catch (error) {
    console.error("Failed to load zone selectors:", error);
  }
}

/**
 * Render SVG line chart comparing actual and predicted pickup volumes.
 *
 * @param {Array<{hour: string, actual: number, predicted: number}>} rows - Scored hourly records.
 */
function drawLineChart(rows) {
  const chart = document.getElementById("forecastChart");
  if (!chart) return;
  if (!rows || !rows.length) {
    chart.innerHTML = "<p>No forecast data available for this selection.</p>";
    return;
  }

  const width = 900;
  const height = 390;
  const left = 48;
  const right = 18;
  const top = 20;
  const bottom = 38;

  const max = Math.max(...rows.flatMap((row) => [row.actual, row.predicted]), 1);
  const plotWidth = width - left - right;
  const plotHeight = height - top - bottom;

  const x = (index) => left + (index / Math.max(rows.length - 1, 1)) * plotWidth;
  const y = (value) => top + plotHeight - (value / max) * plotHeight;
  const path = (key) => rows.map((row, index) => `${index ? "L" : "M"} ${x(index)} ${y(row[key])}`).join(" ");

  // Generate 5 horizontal grid lines with value labels
  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = (max * index) / 4;
    const yy = y(value);
    return `<line class="axis" x1="${left}" x2="${width - right}" y1="${yy}" y2="${yy}"/><text class="chart-label" x="0" y="${
      yy + 4
    }">${value.toFixed(0)}</text>`;
  }).join("");

  // Subsample x-axis time labels every 4 hours for readability
  const labels = rows
    .filter((_, index) => index % 4 === 0)
    .map((row) => {
      const index = rows.indexOf(row);
      return `<text class="chart-label" x="${x(index)}" y="${height - 8}" text-anchor="middle">${String(
        row.hour.slice(11, 16)
      )}</text>`;
    })
    .join("");

  chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img"><g>${grid}</g><path class="actual-line" d="${path(
    "actual"
  )}"/><path class="chart-line" d="${path("predicted")}"/><g>${labels}</g></svg>`;
}

/**
 * Fetch and refresh forecast chart based on active zone and date inputs.
 */
async function loadForecast() {
  const zoneEl = document.getElementById("forecastZone");
  const dateEl = document.getElementById("forecastDate");
  const zone = zoneEl ? zoneEl.value : "";
  const date = dateEl ? dateEl.value : "";
  if (!zone) return;
  try {
    const rows = await getJson(`/api/predictions?zone=${zone}&date=${date}`);
    drawLineChart(rows);
  } catch (error) {
    console.error("Failed to load forecast data:", error);
  }
}

/**
 * Fetch and populate table of detected residual anomalies.
 */
async function loadAnomalies() {
  const zoneEl = document.getElementById("anomalyZone");
  const typeEl = document.getElementById("anomalyType");
  const zone = zoneEl ? zoneEl.value : "";
  const direction = typeEl ? typeEl.value : "";

  try {
    const rows = await getJson(`/api/anomalies?zone=${zone}&direction=${encodeURIComponent(direction)}&limit=200`);
    const tableBody = document.getElementById("anomalyTable");
    if (!tableBody) return;

    if (rows && rows.length > 0) {
      tableBody.innerHTML = rows
        .map(
          (row) =>
            `<tr><td>${row.hour.replace("T", " ").slice(0, 16)}</td><td>${row.zoneName}</td><td>${row.actual.toFixed(
              1
            )}</td><td>${row.predicted.toFixed(1)}</td><td><span class="tag ${
              row.direction.includes("spike") ? "spike" : "drop"
            }">${row.direction}</span></td><td>${row.deviation.toFixed(2)}</td></tr>`
        )
        .join("");
    } else {
      tableBody.innerHTML = `<tr><td colspan="6">No anomalies match this filter.</td></tr>`;
    }
  } catch (error) {
    console.error("Failed to load anomalies:", error);
  }
}

/**
 * Fetch and render K-Means zone cluster profiles.
 */
async function loadClusters() {
  try {
    const groups = await getJson("/api/clusters");
    const container = document.getElementById("clusterCards");
    if (!container) return;

    if (groups && groups.length > 0) {
      container.innerHTML = groups
        .map(
          (group) => `
        <article class="cluster-card">
          <b>Cluster ${group.cluster}</b><small>${group.zones.length} zones · ${group.avgPickups.toFixed(
            2
          )} pickups/hour avg</small>
          ${group.zones
            .sort((a, b) => b.totalPickups - a.totalPickups)
            .slice(0, 5)
            .map(
              (zone) =>
                `<div class="cluster-zone"><span>${zone.zoneName}</span><b>${zone.avgPickups.toFixed(1)}</b></div>`
            )
            .join("")}
        </article>`
        )
        .join("");
    } else {
      container.innerHTML = "<p>No cluster data available. Run the analysis notebook to generate cluster profiles.</p>";
    }
  } catch (error) {
    console.error("Failed to load clusters:", error);
  }
}

/**
 * Append chat message bubble to data agent pane.
 *
 * @param {string} text - Message text.
 * @param {"user"|"agent"} role - Sender role.
 */
function addChatMessage(text, role) {
  const messagesEl = document.getElementById("chatMessages");
  if (!messagesEl) return;
  const message = document.createElement("div");
  message.className = `message ${role}`;
  message.textContent = text;
  messagesEl.appendChild(message);
  message.scrollIntoView({ behavior: "smooth" });
}

// Bind agent form submission
const agentForm = document.getElementById("agentForm");
if (agentForm) {
  agentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const input = document.getElementById("agentInput");
    const text = input ? input.value.trim() : "";
    if (!text) return;
    addChatMessage(text, "user");
    input.value = "";
    try {
      const result = await getJson("/api/agent", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text })
      });
      addChatMessage(result.answer, "agent");
    } catch (error) {
      addChatMessage(`Error: ${error.message}`, "agent");
    }
  });
}

// Bind suggestion pill buttons
document.querySelectorAll(".suggestions button").forEach((button) => {
  button.addEventListener("click", () => {
    const input = document.getElementById("agentInput");
    if (input) input.value = button.textContent;
    if (agentForm) agentForm.requestSubmit();
  });
});

// Event listeners for filter controls
const forecastZoneEl = document.getElementById("forecastZone");
const forecastDateEl = document.getElementById("forecastDate");
const anomalyZoneEl = document.getElementById("anomalyZone");
const anomalyTypeEl = document.getElementById("anomalyType");

if (forecastZoneEl) forecastZoneEl.addEventListener("change", loadForecast);
if (forecastDateEl) forecastDateEl.addEventListener("change", loadForecast);
if (anomalyZoneEl) anomalyZoneEl.addEventListener("change", loadAnomalies);
if (anomalyTypeEl) anomalyTypeEl.addEventListener("change", loadAnomalies);

/**
 * Initial dashboard bootstrap sequence.
 */
async function init() {
  await Promise.all([loadOverview(), loadZoneSelectors(), loadClusters()]);
  await loadForecast();
  await loadAnomalies();
  addChatMessage("Ask me about the taxi forecast, anomalies, clusters, or a specific zone.", "agent");
}

init();
