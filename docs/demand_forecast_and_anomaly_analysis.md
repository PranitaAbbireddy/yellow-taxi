# Demand Forecasting and Anomaly Detection: What Was Analyzed

## Executive summary

The analysis answers two related questions for January 2023:

1. **Demand forecasting:** How many yellow-taxi pickups should be expected in each taxi zone during each hour?
2. **Anomaly detection:** In which zone-hours was the actual number of pickups unexpectedly different from the forecast?

The analysis uses the zone-hour grid already stored in the gold CSV exports:

- 265 taxi zones
- 744 hours from January 1 through January 31, 2023
- 197,160 possible zone-hour records
- One observed pickup count for each zone-hour

The forecasting target is one numeric value:

```text
expected pickups at a zone during a specific hour
```

For example, the model might forecast 214 pickups during one hour in JFK Airport. The actual value is then compared with 214 to calculate a forecast error.

---

## 1. Demand forecast

### What was forecast

The forecast predicts:

```text
target_pickup_count
```

`target_pickup_count` means the number of pickups in one taxi zone during one pickup hour.

The hourly model has this basic input/output relationship:

```text
zone and date/time features
        +
recent pickup history
        +
rolling pickup history
                |
                v
predicted pickup count for that zone-hour
```

### Forecast target and grain

The data grain is:

```text
one zone + one hour
```

An example record is:

```text
JFK Airport
2023-01-01 14:00
242 actual pickups
205 approximately predicted pickups
```

The time key used for the feature tables is:

```text
pickup_zone_id + forecast_hour
```

Zone names and borough names are descriptive attributes. They are not used as the primary model grain.

---

## 2. Features used for forecasting

The model used 11 feature columns from `ml_training_features.csv`.

### Calendar and time features

| Feature | What it describes | Why it may matter |
|---|---|---|
| `hour_of_day` | 0 through 23 | Pickup activity changes by hour, such as commuting and nighttime patterns |
| `day_of_week` | Day number within the week | Weekdays and weekends can have different demand patterns |
| `day_of_month` | 1 through 31 | Captures position within the month |
| `month` | Calendar month | Provides the monthly context, although the training data covers only January |
| `is_weekend` | Whether the hour falls on a weekend | Separates weekend behavior from weekday behavior |

These features are useful because taxi demand follows predictable time patterns:

- morning commuting hours may be busier in some Manhattan zones;
- airport zones may have sustained arrival and departure demand;
- late-night activity may be higher in entertainment areas;
- weekend demand may differ from weekday demand.

### Recent pickup features

| Feature | Meaning | Plain-English example |
|---|---|---|
| `lag_1h` | Pickups in the same zone one hour earlier | How busy the zone was at 1 PM for a 2 PM forecast |
| `lag_24h` | Pickups at the same zone at the same hour yesterday | Monday-at-2-PM demand compared with Sunday-at-2-PM demand |
| `lag_168h` | Pickups at the same zone at the same hour one week earlier | Demand one week ago at the same zone and hour |

Lag features are powerful because actual demand is strongly related to recent demand:

- a busy airport one hour ago is evidence that nearby demand may remain active;
- the previous day can capture daily rhythm;
- the previous week can capture weekly repetition.

### Rolling pickup features

| Feature | Meaning |
|---|---|
| `rolling_mean_24h` | Average pickup count in the zone over the previous 24 hours |
| `rolling_mean_168h` | Average pickup count in the zone over the previous 168 hours, or 7 days |
| `rolling_std_24h` | How much hourly pickup demand changed during the previous 24 hours |

The rolling mean shows the general recent level of demand. The rolling standard deviation shows its instability.

- A zone with steady low demand can have a low rolling mean and low variability.
- A zone with a lunch or commute peak can have rapidly changing demand.
- A high rolling mean does not always mean every hour will be busy, so lag and calendar features remain important.

---

## 3. Handling missing warm-up values

Some lag and rolling values were `"null"` near the beginning of the month. These were literal text values rather than blank CSV cells.

The affected columns were:

- `lag_1h`
- `lag_24h`
- `lag_168h`
- `rolling_mean_24h`
- `rolling_mean_168h`
- `rolling_std_24h`

The beginning of January did not have a full 1-hour, 24-hour, or 168-hour history for every zone. Those warm-up records therefore had no valid historical feature values.

The notebook:

1. Converted `"null"` to a real missing value.
2. Calculated each feature's median using training data.
3. Used those training medians to fill missing values in the training table.
4. Used the same training medians for inference values.

This prevents the inference table from contributing its own distributions and avoids future-information leakage.

The median is used instead of zero because zero could incorrectly imply that a zone had no history. It also preserves the median numeric range for warm-up records.

---

## 4. Forecast model

### Algorithm

The main model was a **Histogram Gradient Boosting Regressor**.

This model learns nonlinear relationships between features. For example, it can learn that:

- demand may rise at a certain hour only when the lag is high;
- different zones may respond differently to the same hour;
- weekend demand has a different pattern from weekday demand;
- rolling variability can distinguish stable zones from volatile zones.

It can also combine weak signals from several features rather than relying on a single feature.

Predictions were clipped so that they could not be negative, since negative pickup counts are impossible.

### Chronological validation

The data was not split randomly because future observations must not help predict past observations.

The notebook:

1. Sorted records by time.
2. Used earlier observations for training.
3. Used later observations as validation data.

This measures how well the model generalizes to a later period within the January sample.

### Forecast baseline

A simple previous-hour baseline was created:

```text
baseline forecast = lag_1h
```

In other words, the baseline says:

> Next hour will have approximately the same pickup count as the previous hour.

The trained model was compared with this baseline.

### Results

| Method | MAE | RMSE | R² |
|---|---:|---:|---:|
| Previous-hour baseline | 4.169 | 13.988 | 0.921 |
| Histogram Gradient Boosting | 2.680 | 8.620 | 0.970 |

The valid baseline comparison values to quote are:

```text
Baseline:         MAE 4.169, RMSE 13.988, R² 0.921
Gradient model:   MAE 2.680, RMSE 8.620, R² 0.970
```

### What the metrics mean

#### MAE: mean absolute error

MAE is the average absolute difference between actual and predicted pickup counts.

```text
MAE = average of absolute(actual - predicted)
```

An MAE of 2.680 means the forecast was off by approximately 2.68 pickups per hour on average across validation records.

MAE is straightforward, but it gives every hour equal weight.

#### RMSE: root mean squared error

RMSE also measures forecast error but gives larger mistakes more weight.

An RMSE of 8.620 means the model has greater error in some large-demand or unusual zone-hours.

#### R²: explained variation

R² describes how much pickup-count variation the model explains compared with a very simple average-only approach.

An R² of 0.970 is approximately 97% of the measured variation in the validation sample, according to this metric.

This does not prove that every individual forecast is accurate. The metric is an aggregate result across all zone-hours and can be strongly influenced by the large number of low-demand zone-hours.

### Output created

The model output was exported to:

```text
data/demand_predictions.csv
```

Each relevant output row contains:

- `pickup_zone_id`
- `zone_name`
- `borough`
- `service_zone`
- `forecast_hour` or `pickup_hour`
- `pickup_count`
- `predicted_pickup_count`
- `residual`

The exported file contains 197,160 prediction rows.

The forecast model was also saved as:

```text
data/demand_hist_gradient_model.joblib
```

---

## 5. How prediction residuals are calculated

The residual measures the difference between what happened and what the model predicted.

```text
Residual = actual pickups - predicted pickups
```

### Residual examples

| Actual | Predicted | Residual | Interpretation |
|---:|---:|---:|---|
| 100 | 80 | +20 | Actual demand was 20 pickups above forecast |
| 25 | 40 | -15 | Actual demand was 15 pickups below forecast |
| 50 | 49 | +1 | Demand agreed closely with forecast |

Residuals are the foundation of the anomaly detector.

Important distinctions:

- **Positive residual:** actual demand was higher than expected.
- **Negative residual:** actual demand was lower than expected.
- **Large residual:** the model was wrong by a noticeable amount.
- **Large residual alone does not prove a real-world cause.**

For example, a positive residual could be caused by an event, unusual weather, a data problem, or a forecast limitation.

---

## 6. Anomaly detection method

The anomaly detector starts with forecast residuals rather than raw pickup counts. This is important because different zones have different normal traffic levels.

A count such as 200 pickups may be normal in one Manhattan zone and extraordinary in a sparse Staten Island zone. Using the residual adapts the definition of unusual behavior to the model's forecast for each zone.

### Zone-specific baseline

For each zone, the notebook calculated:

```text
residual median = typical residual for that zone
MAD = median absolute deviation of residuals in that zone
```

The median describes what normal residual error looks like for the zone:

```text
Typical residual for zone z
```

MAD describes how consistently the residuals cluster around that typical value.

MAD is calculated as:

```text
MAD = median(|residual - median residual|)
```

MAD is preferred over ordinary standard deviation because an anomaly-heavy dataset can contain extreme values that distort a standard deviation.

### Scaled MAD and deviation score

The notebook converted MAD into a robust deviation score using a constant scale of approximately 1.4826:

```text
scaled MAD = MAD × 1.4826
```

The anomaly deviation score was:

```text
anomaly deviation =
    absolute(residual - zone median residual) / scaled MAD
```

A value around 3 means the residual is about three scaled-MAD units away from the zone's typical residual.

### Anomaly threshold

A zone-hour was flagged when:

```text
anomaly deviation >= 3
```

The direction was based on the residual:

| Residual compared with typical residual | Direction |
|---|---|
| Above threshold | `unexpected spike` |
| Below threshold | `unexpected drop` |

### Example interpretation

Suppose Newark Airport has:

- typical residual median: -0.295
- scaled MAD: 0.443
- one actual hour with residual: 2.421

The deviation can be calculated as:

```text
(2.421 - -0.295) / 0.443 = about 6.13
```

Because 6.13 is above 3, this hour is marked anomalous. The positive residual also makes it an unexpected spike.

---

## 7. Anomaly results

The full anomaly output was written to:

```text
data/demand_anomalies.csv
```

It contains **18,286 anomalous zone-hours**:

| Direction | Count |
|---|---:|
| Unexpected spikes | 15,343 |
| Unexpected drops | 2,943 |
| Total | 18,286 |

The observed residual range in the output was approximately:

```text
-175.775 to +273.783 pickups
```

### Reading the anomaly output

The anomaly CSV contains:

- `pickup_zone_id`
- `zone_name`
- `borough`
- `pickup_hour`
- `pickup_count`
- `predicted_pickup_count`
- `residual`
- `residual_median`
- `residual_mad`
- `anomaly_deviation`
- `is_anomaly`
- `anomaly_direction`

The important columns during analysis are:

1. **`pickup_count`**: what actually happened.
2. **`predicted_pickup_count`**: what the model expected.
3. **`residual`**: actual minus predicted.
4. **`anomaly_deviation`**: how unusual the residual is for the zone.
5. **`anomaly_direction`**: spike or drop.

### What is the anomaly rate

18,286 anomalies occurred in 197,160 possible zone-hours:

```text
18,286 / 197,160 = approximately 9.27%
```

This rate does not establish that 9.27% of taxi demand was unusual. It establishes that 9.27% of zone-hour forecast residuals crossed the notebook's chosen 3-scaled-MAD threshold.

A threshold change would change the anomaly count.

---

## 8. Simple examples

### Newark Airport at midnight

Observed:

- predicted pickups: approximately 18.217
- actual pickups: 0
- residual: approximately -18.217

The value is treated as an unexpected drop because it differs greatly from the normal Newark Airport residual pattern.

This may reflect:

- normal sparse demand in a particular hour;
- forecasting weakness;
- missing or incomplete observations;
- an actual operational or demand change.

The CSV flag alone cannot distinguish those causes.

### Newark Airport at a busier hour

Observed:

- actual pickups: 6
- predicted pickups: approximately 1.034
- residual: approximately 4.966

The value was flagged because 6 actual pickups differed from the 1.034 forecast by more than the zone's robust threshold.

The analyst should inspect nearby hours, zone characteristics, and day-specific context before drawing conclusions.

---

## 9. Features that deserve attention when analyzing anomalies

An analyst should review the following features together rather than treating one column as the complete explanation.

### Primary forecast columns

| Column | Question to ask |
|---|---|
| `pickup_count` | What was observed? |
| `predicted_pickup_count` | What would normal expected demand be? |
| `residual` | How many pickups above or below normal? |
| `anomaly_deviation` | Is the difference unusual for this particular zone? |
| `anomaly_direction` | Is it an unexpected spike or drop? |

### Zone context

| Column | Why it matters |
|---|---|
| `zone_name` | Identifies the physical location |
| `borough` | Allows city-area comparisons |
| `service_zone` | Distinguishes airport, yellow-zone, or borough-zone demand patterns |

### Time context

| Feature | Why it matters |
|---|---|
| Hour of day | Demand may be normal at one hour and unusual at another |
| Day of week | Weekends can have distinct patterns |
| Date | Supports weather, holiday, event, and disruption comparison |
| Forecast vs actual difference | Separates a high count from an unusual count |

### Forecast history

The feature table is also useful for investigating whether the model had enough recent information:

| Feature | Investigation question |
|---|---|
| `lag_1h` | Did an immediate demand change occur? |
| `lag_24h` | Did the previous day at this hour look similar? |
| `lag_168h` | Did demand look similar at the same hour one week ago? |
| `rolling_mean_24h` | Was the current day trending unusually high or low? |
| `rolling_std_24h` | Was recent demand already unstable? |
| Warm-up null values | Was the zone still missing useful history? |

---

## 10. Suggested analysis workflow

### First: validate the forecast

1. Compare actual and predicted pickups by zone.
2. Check MAE and RMSE rather than looking only at one zone-hour.
3. Inspect periods where absolute residuals are highest.
4. Compare performance for high-demand and low-demand zones separately.
5. Compare gradient-boosting error with the previous-hour baseline.

### Second: review anomalies

1. Filter by `unexpected spike` or `unexpected drop`.
2. Group anomalies by zone and borough.
3. Review dates and hours instead of isolated rows.
4. Examine whether repeated anomalies are concentrated in one zone or hour.
5. Compare anomaly direction with residual magnitude and deviation score.

### Third: investigate root causes

For a possible spike, check:

- concerts, sporting events, conferences, or holidays;
- weather disruption or transit changes;
- unusual traffic or airport activity;
- bursts at nearby zones;
- source or collection errors.

For a possible drop, check:

- missing data or delayed ingestion;
- driver availability or service outages;
- weather or travel disruption;
- a zone with normally sparse observations;
- an overprediction by the model.

### Fourth: avoid overinterpretation

An anomaly is not automatically:

- a taxi service failure;
- a fraud case;
- evidence of an event;
- proof that the model is wrong;
- proof that actual data is incorrect.

It is a statistical flag that should trigger review.

---

## 11. Known limitations

### January-only coverage

The data covers only January 2023. Patterns from other seasons are not represented.

### Retrospective scoring

The inference table is scored within the available January period. It does not provide evidence for future January predictions or future months.

### Warm-up history

Early January records have less reliable lag and rolling history.

### Sparse zones

Zones with very few pickups can appear highly anomalous even when the absolute difference is small. A single unexpected pickup may create a large residual deviation in a normally empty zone.

### Forecast median treatment

Training medians are reasonable for warm-up values, but they are an approximation. They do not reconstruct real historical demand.

### MAD threshold

The 3-scaled-MAD threshold controls the anomaly count. It is a reasonable review threshold, but no threshold is universally correct.

### No external context

The analysis does not include:

- weather;
- holidays;
- events;
- traffic congestion;
- subway disruptions;
- road closures;
- known taxi policy changes.

Adding those features could improve future forecasting and anomaly interpretation.

### Dataset grain

The model predicts one zone-hour total. It does not forecast individual trips, pickup locations within a zone, trip durations, or fares.

---

## 12. Where to review results

| File | Purpose |
|---|---|
| `data/ml_training_features.csv` | Forecasting model features and training target |
| `data/ml_inference_features.csv` | Same feature shape used for scoring |
| `data/demand_predictions.csv` | Actual, predicted, and residual values for every zone-hour |
| `data/demand_anomalies.csv` | Subset of forecast residuals flagged as anomalies |
| `data/demand_hist_gradient_model.joblib` | Saved forecast model |
| `notebooks/analysis.ipynb` | Notebook implementation |
| `notebooks/analysis.executed.ipynb` | Notebook with the successful execution results |

The final executed notebook is the best record of the exact implementation and executed values. This document explains those values in analysis terms so they can be presented without assuming deep machine-learning knowledge.
