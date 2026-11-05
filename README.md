# NYC Yellow Taxi Demand Analysis

An end-to-end NYC Yellow Taxi project that builds a gold zone-hour data
platform, trains an hourly pickup-demand forecasting model, detects unusual
demand residuals, groups zones by demand behavior, and serves the results in a
local web dashboard and data agent.

> The sample analysis covers 265 taxi zones across January 2023. It is a
> January retrospective analysis, not a production real-time forecasting
> system.

## Project overview

The repository contains:

- Bronze-to-gold data engineering code for Databricks
- Gold ML training and inference feature contracts
- A Jupyter notebook for demand forecasting, anomaly detection, and clustering
- A Node.js dashboard for forecasts, anomalies, clusters, and model metrics
- A CSV-backed conversational agent for zone-level questions
- Evaluation scripts for forecast error and anomaly-threshold analysis

The main forecasting problem is:

```text
Given a taxi zone, an hour, calendar features, and recent pickup history,
predict the expected number of pickups for that zone-hour.
```

## What the analysis does

### Hourly demand forecasting

The notebook trains a HistGradientBoostingRegressor to predict:

```text
target_pickup_count
```

The model uses:

- Hour of day
- Day of week
- Day of month
- Month
- Weekend indicator
- Pickups one hour earlier
- Pickups 24 hours earlier
- Pickups 168 hours earlier
- 24-hour rolling mean
- 168-hour rolling mean
- 24-hour rolling standard deviation

The notebook uses a chronological 80/20 split instead of random train/test
splitting. Earlier January observations are used for training and later
observations are used for validation.

Main held-out validation metrics:

| Method | MAE | RMSE | R² |
|---|---:|---:|---:|
| Previous-hour baseline (`lag_1h`) | 4.169 | 13.988 | 0.921 |
| HistGradientBoosting | 2.680 | 8.620 | 0.970 |

MAE and RMSE are measured in pickups per zone-hour. The gradient-boosting model
should therefore be read alongside these baseline values rather than by R² alone.

### Anomaly detection

Anomalies are calculated from forecast residuals:

```text
residual = actual pickup count - predicted pickup count
```

For each taxi zone, the analysis calculates:

- Median residual
- Median absolute deviation, or MAD
- Robust deviation in scaled-MAD units

The current anomaly threshold is three scaled-MAD units. Rows above this threshold
are divided into:

- `unexpected spike`: actual demand was unusually higher than forecast
- `unexpected drop`: actual demand was unusually lower than forecast

The threshold is a review signal, not proof that an event occurred or that data
is incorrect.

### Zone clustering

K-Means with four clusters groups zones using:

- Average hourly pickups
- Pickup count variability
- Total monthly pickups
- Weekend pickup share
- Average pickup count for all 24 hours

Cluster numbers are descriptive labels and do not represent a ranked quality
level.

## Web dashboard and agent

The dashboard provides:

- Demand overview
- Actual-versus-predicted hourly charts
- Zone and direction anomaly filters
- K-Means cluster profiles
- Agent chat

The agent is currently deterministic and runs locally. It reads the generated
CSV outputs and identifies a zone or question type before returning an answer.
It does not call an external LLM or send data outside the application.

Examples:

- `Which zones have the highest total demand?`
- `Which zones have the most anomalies?`
- `Forecast for JFK Airport`
- `Anomalies for Newark Airport`
- `What cluster is Times Sq/Theatre District in?`
- `Show model accuracy`

## Repository layout

```text
app/
  public/                 Browser dashboard
  server.js               Express API, web server, and local agent
data/                     Generated ML CSV and model artifacts, normally ignored
docs/
  architecture.md         Platform architecture
  demand_forecast_and_anomaly_analysis.md
  model_evaluation.md     Metric definitions and evaluation plan
  validation_report.md
notebooks/
  analysis.ipynb          Forecast, anomaly, and clustering workflow
  analysis.executed.ipynb Successful executed notebook copy
scripts/
  evaluate_demand.js      Node evaluation report generator
src/
  nyc_taxi_data_platform/ Bronze, silver, gold, and pipeline code
tests/                    Unit tests
```

## Prerequisites

For the data engineering and notebook portions:

- Windows PowerShell
- Python 3.10 or later
- Java 11 or later for local PySpark tests
- Databricks CLI for Databricks deployment

For the dashboard:

- Node.js 20 or later
- npm

## Python setup

Create a local environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

Run local unit tests:

```powershell
pytest tests/unit -q
```

Or run the repository helper:

```powershell
.\scripts\run_local_tests.ps1
```

## Run the analysis notebook

Open:

```text
notebooks/analysis.ipynb
```

Run all cells. The notebook loads the four gold CSV exports, validates keys,
imputes warm-up feature values using training medians, trains and validates the
model, scores the inference rows, detects anomalies, groups zones, and writes
generated artifacts under `data/`.

The main generated files are:

```text
demand_predictions.csv
demand_anomalies.csv
zone_demand_clusters.csv
demand_hist_gradient_model.joblib
zone_demand_kmeans.joblib
```

## Run the web dashboard

Install JavaScript dependencies:

```powershell
npm install
```

Start the application:

```powershell
npm start
```

Open:

```text
http://localhost:3000
```

Use a custom port if needed:

```powershell
$env:PORT='3001'
npm start
```

## Evaluate the predictions

Generate error metrics and threshold sensitivity:

```powershell
npm run evaluate
```

This creates:

- `data/forecast_metrics_summary.csv`
- `data/forecast_metrics_by_zone.csv`
- `data/forecast_metrics_by_hour.csv`
- `data/anomaly_threshold_sensitivity.csv`

The evaluation endpoint is:

```text
GET /api/evaluation
```

Use MAE and RMSE as the primary forecasting metrics. Add WAPE and thresholded
accuracy when percentage interpretation is useful. Avoid treating raw MAPE as
the main score because it is unstable for zero-demand zone-hours.

See [docs/model_evaluation.md](docs/model_evaluation.md) for a detailed metric
and validation plan.

## Dashboard API

The Express server exposes:

```text
GET  /api/summary
GET  /api/zones?q=<query>
GET  /api/predictions?zone=<zone-id>&date=<YYYY-MM-DD>
GET  /api/anomalies?zone=<zone-id>&direction=<direction>&limit=<count>
GET  /api/clusters
GET  /api/evaluation
POST /api/agent
```

Agent requests use:

```json
{
  "message": "Which zones have the highest total demand?"
}
```

## Data files

The repository expects generated CSV files in `data/`. The data folder is
gitignored because it can contain large ML artifacts and exported datasets.

The four source gold exports used by the notebook are:

```text
dim_taxi_zone.csv
fact_pickups_hourly.csv
ml_training_features.csv
ml_inference_features.csv
```

The complete zone-hour grid has 265 zones and 744 January 2023 hours, totaling
197,160 records.

## Databricks configuration

The Python package implements a Bronze-Silver-Gold data platform. Default
configuration is stored in `config/defaults.yaml`.

Important environment variables:

```text
NYC_TAXI_CATALOG
NYC_TAXI_VOLUME_BASE
```

Authenticate and deploy with:

```powershell
databricks auth login -p DEFAULT
databricks bundle validate -t dev
databricks bundle deploy -t dev
databricks bundle run nyc_taxi_pipeline -t dev
```

Deployment availability depends on the Databricks workspace, edition, and
permissions.

## Documentation

- [Data engineering architecture](docs/architecture.md)
- [Source schemas](docs/source_schemas.md)
- [Data dictionary](docs/data_dictionary.md)
- [Feature contract](docs/feature_contract.md)
- [Forecast and anomaly explanation](docs/demand_forecast_and_anomaly_analysis.md)
- [Model evaluation guide](docs/model_evaluation.md)
- [ML handoff](docs/ml_handoff.md)
- [Data quality decisions](docs/data_quality.md)
- [Validation report](docs/validation_report.md)
- [Architecture decisions](docs/decisions.md)

## Limitations

- The analysis covers January 2023 only.
- It does not include weather, holidays, major events, traffic, transit, or
  road closure data.
- The original validation is retrospective and chronological.
- Warm-up lag and rolling values are median-imputed.
- Sparse zones may produce unstable percentage and anomaly results.
- Anomaly detection is based on forecast residuals, so forecast error can
  become anomaly error.
- The current agent is a deterministic CSV query agent, not an external
  generative LLM agent.

## Recommended next steps

- Add rolling-origin validation folds.
- Compare additional baseline models.
- Add weather and event context.
- Add labeled anomaly records and precision/recall evaluation.
- Segment accuracy by zone demand and hour.
- Add authentication and database persistence before production deployment.
- Replace the deterministic agent with an LLM tool-calling agent guarded by
  explicit allowed tools and data scopes.
