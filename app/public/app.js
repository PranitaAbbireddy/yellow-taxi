const state = { zones: [] };

const formatNumber = (value) => Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 1 });

async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error((await response.json()).error || "Request failed");
  return response.json();
}

function switchPage(page) {
  document.querySelectorAll(".page").forEach((el) => el.classList.remove("active"));
  document.querySelectorAll(".nav-button").forEach((el) => el.classList.remove("active"));
  document.getElementById(page).classList.add("active");
  document.querySelector(`[data-page="${page}"]`).classList.add("active");
  document.getElementById("pageTitle").textContent = {
    overview: "Demand overview", forecast: "Hourly forecasting", anomalies: "Anomaly detection", clusters: "Zone segmentation", agent: "Taxi data agent"
  }[page];
}

document.querySelectorAll(".nav-button").forEach((button) => button.addEventListener("click", () => switchPage(button.dataset.page)));

async function loadOverview() {
  const [summary, clustersData] = await Promise.all([
    getJson("/api/summary"),
    getJson("/api/clusters")
  ]);
  document.getElementById("summaryCards").innerHTML = [
    ["Taxi zones", summary.zoneCount],
    ["Hourly forecasts", summary.forecastCount.toLocaleString()],
    ["Anomalies detected", summary.anomalyCount.toLocaleString()],
    ["Model MAE", "2.680"]
  ].map(([label, value]) => `<article class="card"><span>${label}</span><strong>${value}</strong></article>`).join("");

  const allZones = await getJson("/api/zones");
  state.zones = [...allZones];

  const topDemand = [...await Promise.all(allZones.map(async (zone) => {
    const rows = await getJson(`/api/predictions?zone=${zone.pickup_zone_id}`);
    return { name: zone.zone_name, total: rows.reduce((sum, row) => sum + row.actual, 0) };
  }))].sort((a, b) => b.total - a.total).slice(0, 6);
  const max = topDemand[0]?.total || 1;
  document.getElementById("busyZones").innerHTML = topDemand.map((row) =>
    `<div class="bar-row"><span>${row.name}</span><div class="bar-track"><div class="bar-fill" style="width:${100 * row.total / max}%"></div></div><b>${formatNumber(row.total)}</b></div>`
  ).join("");
  document.getElementById("anomalyMix").innerHTML = `
    <div class="mix-card spike"><strong>${summary.spikeCount.toLocaleString()}</strong><span>Unexpected spikes</span></div>
    <div class="mix-card drop"><strong>${summary.dropCount.toLocaleString()}</strong><span>Unexpected drops</span></div>`;
}

async function loadZoneSelectors() {
  const zones = await getJson("/api/zones");
  const options = zones.map((zone) => `<option value="${zone.pickup_zone_id}">${zone.zone_name}</option>`).join("");
  document.getElementById("forecastZone").innerHTML = options;
  document.getElementById("anomalyZone").insertAdjacentHTML("beforeend", options);
}

function drawLineChart(rows) {
  const chart = document.getElementById("forecastChart");
  if (!rows.length) { chart.innerHTML = "<p>No data for this selection.</p>"; return; }
  const width = 900, height = 390, left = 48, right = 18, top = 20, bottom = 38;
  const max = Math.max(...rows.flatMap((row) => [row.actual, row.predicted]), 1);
  const plotWidth = width - left - right, plotHeight = height - top - bottom;
  const x = (index) => left + index / Math.max(rows.length - 1, 1) * plotWidth;
  const y = (value) => top + plotHeight - value / max * plotHeight;
  const path = (key) => rows.map((row, index) => `${index ? "L" : "M"} ${x(index)} ${y(row[key])}`).join(" ");
  const grid = Array.from({ length: 5 }, (_, index) => {
    const value = max * index / 4;
    const yy = y(value);
    return `<line class="axis" x1="${left}" x2="${width-right}" y1="${yy}" y2="${yy}"/><text class="chart-label" x="0" y="${yy+4}">${value.toFixed(0)}</text>`;
  }).join("");
  const labels = rows.filter((_, index) => index % 4 === 0).map((row) => {
    const index = rows.indexOf(row);
    return `<text class="chart-label" x="${x(index)}" y="${height-8}" text-anchor="middle">${String(row.hour.slice(11,16))}</text>`;
  }).join("");
  chart.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img"><g>${grid}</g><path class="actual-line" d="${path("actual")}"/><path class="chart-line" d="${path("predicted")}"/><g>${labels}</g></svg>`;
}

async function loadForecast() {
  const zone = document.getElementById("forecastZone").value;
  const date = document.getElementById("forecastDate").value;
  drawLineChart(await getJson(`/api/predictions?zone=${zone}&date=${date}`));
}

async function loadAnomalies() {
  const zone = document.getElementById("anomalyZone").value;
  const direction = document.getElementById("anomalyType").value;
  const rows = await getJson(`/api/anomalies?zone=${zone}&direction=${encodeURIComponent(direction)}&limit=200`);
  document.getElementById("anomalyTable").innerHTML = rows.map((row) =>
    `<tr><td>${row.hour.replace("T"," ").slice(0,16)}</td><td>${row.zoneName}</td><td>${row.actual.toFixed(1)}</td><td>${row.predicted.toFixed(1)}</td><td><span class="tag ${row.direction.includes("spike") ? "spike" : "drop"}">${row.direction}</span></td><td>${row.deviation.toFixed(2)}</td></tr>`
  ).join("") || `<tr><td colspan="6">No anomalies match this filter.</td></tr>`;
}

async function loadClusters() {
  const groups = await getJson("/api/clusters");
  document.getElementById("clusterCards").innerHTML = groups.map((group) => `
    <article class="cluster-card">
      <b>Cluster ${group.cluster}</b><small>${group.zones.length} zones · ${group.avgPickups.toFixed(2)} pickups/hour avg</small>
      ${group.zones.sort((a,b) => b.totalPickups-a.totalPickups).slice(0,5).map((zone) => `<div class="cluster-zone"><span>${zone.zoneName}</span><b>${zone.avgPickups.toFixed(1)}</b></div>`).join("")}
    </article>
  `).join("");
}

function addChatMessage(text, role) {
  const message = document.createElement("div");
  message.className = `message ${role}`;
  message.textContent = text;
  document.getElementById("chatMessages").appendChild(message);
  message.scrollIntoView();
}

document.getElementById("agentForm").addEventListener("submit", async (event) => {
  event.preventEventDefault?.();
  event.preventDefault();
  const input = document.getElementById("agentInput");
  const text = input.value.trim();
  if (!text) return;
  addChatMessage(text, "user");
  input.value = "";
  try {
    const result = await getJson("/api/agent", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({message:text}) });
    addChatMessage(result.answer, "agent");
  } catch (error) {
    addChatMessage(error.message, "agent");
  }
});

document.querySelectorAll(".suggestions button").forEach((button) => button.addEventListener("click", () => {
  document.getElementById("agentInput").value = button.textContent;
  document.getElementById("agentForm").requestSubmit();
}));
document.getElementById("forecastZone").addEventListener("change", loadForecast);
document.getElementById("forecastDate").addEventListener("change", loadForecast);
document.getElementById("anomalyZone").addEventListener("change", loadAnomalies);
document.getElementById("anomalyType").addEventListener("change", loadAnomalies);

async function init() {
  await Promise.all([loadOverview(), loadZoneSelectors(), loadClusters()]);
  await loadForecast();
  await loadAnomalies();
  addChatMessage("Ask me about the taxi forecast, anomalies, clusters, or a specific zone.", "agent");
}
init();
