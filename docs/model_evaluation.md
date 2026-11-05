# Model Evaluation Guide

## Use two different kinds of metrics

There are two separate questions:

1. **Forecast evaluation:** Did the model predict pickup counts accurately?
2. **Anomaly evaluation:** Did the anomaly system correctly identify known unusual events?

Forecast accuracy can be measured directly with the actual pickup count. Anomaly accuracy cannot be measured correctly without a labeled event list.

## Forecast metrics currently available

Run:

```powershell
npm run evaluate
```

The current full-January scoring output reports:

| Metric | Result |
|---|---:|
| Rows scored | 197,160 |
| MAE | 2.489 pickups/hour |
| RMSE | 7.860 pickups/hour |
| R² | 0.974 |
| WAPE | 16.001% |
| Demand-weighted accuracy (`100 - WAPE`) | 83.999% |
| Median absolute error | 0.220 pickups |
| P95 absolute error | 13.791 pickups |
| Predictions within 1 pickup | 74.432% |
| Predictions within 5 pickups | 88.252% |

These numbers evaluate the available full-January predictions. They are not the
held-out chronological validation score because the model is also compared with
its actual values throughout the scored period. Keep the notebook's separate
chronological validation metrics for model-selection claims.

The script reads `data/demand_predictions.csv` and creates:

- `data/forecast_metrics_summary.csv`
- `data/forecast_metrics_by_zone.csv`
- `data/forecast_metrics_by_hour.csv`
- `data/anomaly_threshold_sensitivity.csv`

### Recommended primary metrics

| Metric | Meaning | When to use it |
|---|---|---|
| MAE | Average absolute pickup-count error | Primary overall metric |
| RMSE | Error while giving more weight to large mistakes | High-demand and extreme-error review |
| WAPE | Error as a percentage of total actual demand | Best simple percentage metric for many zero-heavy records |
| sMAPE | Symmetric percentage error | Useful comparison for nonzero actual and predicted values |
| Median absolute error | Typical error without extreme-value influence | Useful for sparse zones |
| P95 absolute error | Error below which 95% of records fall | Tail-risk measurement |
| R² | Proportion of overall variation explained | Secondary; interpretation changes for count mixtures |

MAE is the recommended primary metric because pickup counts are straightforward and every pickup is a comparable unit. RMSE should be reported second because it highlights large forecasting mistakes.

### Metrics to avoid or label carefully

#### Raw MAPE

MAPE divides by actual pickup count. It is unstable when actual demand is zero or close to zero. Many sparse taxi zone-hours have zero pickups, so a raw percentage accuracy result can become misleading.

#### One overall accuracy percentage

A statement such as “95% accurate” is ambiguous unless it defines the threshold, for example:

```text
within one pickup: X%
within five pickups: Y%
```

Demand-weighted accuracy is also valid only as a complement to MAE and should be interpreted as `100 - WAPE`.

#### R² alone

R² can be high because zero-heavy zone-hours are easy or difficult to forecast overall. It should not replace MAE and RMSE.

## Validation setup

The notebook currently uses one chronological validation split:

- Earlier January observations train the model.
- Later January observations validate it.
- There is no random row split.

For stronger evidence, add rolling-origin validation:

1. Train through January 5, validate January 6–10.
2. Train through January 10, validate January 11–15.
3. Train through January 15, validate January 16–20.
4. Train through January 20, validate January 21–25.
5. Train through January 25, validate January 26–31.

Report the mean, median, minimum, and maximum of MAE and RMSE across folds. This helps show whether performance is stable or dependent on one month period.

Do not use a random K-fold split for this dataset because it would place future observations in the training set.

## Evaluate by segment

### By zone

`forecast_metrics_by_zone.csv` measures:

- MAE
- RMSE
- MAPE-related metrics
- Median error
- P95 error
- The percentage of predictions within 1 and 5 pickups

Review the highest-MAE and highest-RMSE zones separately. This identifies whether one zone dominates the model's overall error.

Also review:

- high-demand zones;
- low-demand and sparse zones;
- airport zones;
- Manhattan versus outer boroughs;
- unusually volatile zones.

### By hour

`forecast_metrics_by_hour.csv` identifies commuting, airport, evening, and overnight periods with different errors.

Look for recurring patterns such as:

- morning or evening commuting peaks;
- overnight sparse zone-hours;
- transition periods around demand changes.

### By actual-demand bins

Group validation records by pickup count, for example:

- 0 pickups
- 1–5 pickups
- 6–20 pickups
- 21–50 pickups
- 51–100 pickups
- above 100 pickups

This prevents overall MAE from hiding poor performance in the busiest zones.

## Backtesting and baseline comparison

Always retain comparison baselines:

1. Previous-hour `lag_1h` baseline.
2. Same-hour yesterday `lag_24h` baseline.
3. Same-hour previous-week `lag_168h` baseline.
4. Zone-specific seasonal median.
5. Overall mean predictor.
6. HistGradientBoosting model.

The ML model should beat a simple baseline repeatedly before being considered valuable.

Metrics should be reported on all baselines using the same chronological validation rows.

## Feature importance

Permutation importance is useful for directional understanding:

- Shuffle one feature.
- Measure the increase in validation MAE.
- Repeat several times.
- Larger increases indicate stronger validation dependence.

Important caveats:

- Correlated features can share importance.
- A feature may have low permutation importance while still contributing through interactions.
- Importance does not prove causation.
- Negative or near-zero values indicate little validation benefit.

## Anomaly evaluation

### Threshold sensitivity

`anomaly_threshold_sensitivity.csv` compares scaled-MAD thresholds.

Do not select a threshold only by reducing the anomaly count. A better threshold should balance:

- false alarms;
- missed unusual demand;
- analyst review capacity;
- operational importance.

In this dataset, common threshold values are:

| Threshold | Expected behavior |
|---|---|
| 2.0 scaled MAD | More flags; higher sensitivity; more false alarms |
| 3.0 scaled MAD | Current notebook threshold |
| 4.0 scaled MAD | Fewer flags; misses less obvious events |

### Labeled-event benchmark

To calculate precision, recall, F1, and false-alarm rate, create one CSV with actual known anomalous zone-hours:

```text
pickup_zone_id, pickup_hour, label, optional_event_type
```

Labels should be:

- `1` for a confirmed anomaly;
- `0` for a confirmed normal hour.

The anomaly evaluator can then calculate:

```text
Precision = confirmed anomalies detected / total anomalies detected
Recall = confirmed anomalies detected / all confirmed anomalies
F1 = 2 * precision * recall / (precision + recall)
False alarms per day = normal hours flagged / number of days
Detection delay = first detected hour - event start hour
```

Useful labels may come from:

- known weather alerts;
- major event calendars;
- airport schedule disruptions;
- known data-quality incidents;
- manually reviewed taxi-demand spikes or drops.

Without these labels, it is misleading to claim anomaly “accuracy.”

## Reproducible reporting format

Each evaluation report should include:

- Dataset and date range.
- Zone-hour row count.
- Validation date and chronological cutoff.
- Feature imputation method.
- Baseline definitions.
- MAE, RMSE, WAPE, R².
- Metrics by high-demand and sparse zone.
- Metrics by hour.
- Anomaly threshold and sensitivity.
- Number of anomaly labels.
- Known limitations.

## Recommended next implementation

1. Keep MAE, RMSE, and WAPE as the primary forecast scorecard.
2. Add four or five rolling-origin validation folds.
3. Compare the model with lag-24 and lag-168 baselines.
4. Export model metrics to one stable CSV.
5. Add metrics by zone, hour, and demand bin to the notebook.
6. Create a labeled anomaly workbook for precision, recall, and F1.
7. Add these metric outputs to the web dashboard.
