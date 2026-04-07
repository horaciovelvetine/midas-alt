## Pipeline

| Step | Script | Purpose |
|------|--------|---------|
| 1 | `get_airforce_weather_v2.py` | Current conditions + 7-day API forecast from Open-Meteo |
| 2 | `fetch_air_force_historical_weather.py` | 3 years of daily ERA5 reanalysis per base |
| 3 | `kmeans_weather_clustering.py` | K-Means (K=3): Warm, Cool, Cold & Wet clusters |
| 4 | `individual_base_analysis.py` | Per-base and per-cluster weather heatmaps |
| 5 | `af_weather_weekly_model.py` | Trains XGBoost on 3-year history, predicts next 7 days recursively |
| 6 | `build_degradation_risk.py` | Converts 7-day forecast into degradation risk scores per base per system |

## Weather Model

XGBoost `MultiOutputRegressor` for continuous targets + `XGBClassifier` for weather code. Trained on ~80,000+ daily samples across all bases. Predicts day-by-day recursively — each predicted day feeds back as lagged features for the next.

Features per base: 1/7/14-day lags, 7-day rolling means, sin/cos cyclical encoding (day-of-year, month), latitude/longitude, cluster ID. Precipitation targets use `log1p` transform. Wind direction uses sin/cos decomposition. Validated with TimeSeriesSplit cross-validation (3 folds).

## Degradation Risk Scoring

Rule-based system — no failure labels needed. Converts the 7-day forecast into infrastructure risk using known physics of how weather degrades building materials.

**Stage 1 — Aggregate 7-day stressors per base:** freeze-thaw cycle count, total precipitation/rain/snow, precipitation hours, max wind gust, avg wind speed, avg max humidity, peak apparent temperature, avg daily temp swing, max consecutive wet days, avg cloud cover.

**Stage 2 — Normalize each stressor to 0–100** using damage-onset thresholds (e.g., 5 freeze-thaw days/week = 100, 75mm rain/week = 100, wind gusts scale from 20 km/h onset to 100 km/h ceiling).

**Stage 3 — Weighted combination into 6 system-type risk scores:**

| System | Primary Drivers |
|--------|----------------|
| Roofing | Wind (0.30), rain (0.25), freeze-thaw (0.20) |
| Electrical / Controls | Humidity (0.30), heat (0.25), wet streak (0.15) |
| Pavement / Foundations | Freeze-thaw (0.30), temp swing (0.25), rain (0.20) |
| HVAC / Mechanical | Heat (0.30), temp swing (0.25), humidity (0.20) |
| Exterior Envelope | Wind (0.25), rain (0.25), freeze-thaw (0.20) |
| Plumbing / Water | Freeze-thaw (0.35), temp swing (0.25), rain (0.20) |

**Stage 4 — Overall infrastructure risk:** weighted average across all 6 systems (roofing 0.25, pavement 0.20, electrical 0.20, HVAC 0.15, envelope 0.10, plumbing 0.10).

**Stage 5 — Risk bands:** Low (0–25), Moderate (26–50), High (51–75), Critical (76–100).

## MIDAS Integration

Output includes `midas_weather_multiplier` per base: `1.0 + (overall_risk / 100) × 0.5`, ranging from 1.0 (benign weather) to 1.5 (extreme weather). Applied to MIDAS facility condition index degradation rates. System-specific risk scores can also drive per-system degradation individually through MIDAS dependency chains.

## Data Sources

- **Base list:** `midas_config_values.xlsx` (BTS ArcGIS FeatureServer)
- **Historical weather:** Open-Meteo ERA5 Archive API (3 years daily)
- **Forecast weather:** Open-Meteo Forecast API
