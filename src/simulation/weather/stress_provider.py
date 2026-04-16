"""
Weather stress provider for the MIDAS condition index model.

Converts per-base 7-day weather forecast data into a normalized stress
value (0.0 - 1.0) suitable for FacilityConditionModel.step(weather_stress=...).

The computation pipeline is lifted directly from the weather team's
build_degradation_risk.py (Weather-T1), preserving their system weights
and normalization thresholds exactly. The only change is that we expose
the result as a clean per-base lookup rather than a standalone script.

Pipeline:
    forecast CSV
        aggregate_stressors()   raw weather metrics per base
        normalize_scores()      0-100 component scores
        compute_system_risks()  per-system-type risk scores
        compute_overall_risk()  single 0-100 composite score
        / 100                   normalized 0-1 weather_stress
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


_DEFAULT_FORECAST = Path(__file__).parent / "data" / "all_bases_7day_forecast.csv"

# System/component weights (I got dis from weathers build_degradation_risk.py) 
_SYSTEM_WEIGHTS: dict[str, dict[str, float]] = {
    "roofing":    {"wind": 0.30, "rain": 0.25, "freeze_thaw": 0.20, "snow": 0.10, "wetness": 0.10, "temp_swing": 0.05},
    "electrical": {"humidity": 0.30, "heat": 0.25, "wet_streak": 0.15, "rain": 0.15, "wind": 0.10, "temp_swing": 0.05},
    "pavement":   {"freeze_thaw": 0.30, "temp_swing": 0.25, "rain": 0.20, "wetness": 0.10, "snow": 0.10, "wind": 0.05},
    "hvac":       {"heat": 0.30, "temp_swing": 0.25, "humidity": 0.20, "freeze_thaw": 0.15, "wind": 0.10},
    "envelope":   {"wind": 0.25, "rain": 0.25, "freeze_thaw": 0.20, "temp_swing": 0.15, "humidity": 0.10, "snow": 0.05},
    "plumbing":   {"freeze_thaw": 0.35, "temp_swing": 0.25, "rain": 0.20, "humidity": 0.10, "wetness": 0.10},
}

_OVERALL_WEIGHTS: dict[str, float] = {
    "roofing": 0.25, "pavement": 0.20, "electrical": 0.20,
    "hvac": 0.15, "envelope": 0.10, "plumbing": 0.10,
}

# Column name map (forecast CSV to stressor key)
_COL = {
    "temp_max":        "daily_temperature_2m_max",
    "temp_min":        "daily_temperature_2m_min",
    "apparent_temp_max": "daily_apparent_temperature_max",
    "precip_sum":      "daily_precipitation_sum",
    "rain_sum":        "daily_rain_sum",
    "snowfall_sum":    "daily_snowfall_sum",
    "precip_hours":    "daily_precipitation_hours",
    "wind_gust_max":   "daily_wind_gusts_10m_max",
    "wind_speed_mean": "daily_wind_speed_10m_mean",
    "humidity_max":    "daily_relative_humidity_2m_max",
    "cloud_cover":     "daily_cloud_cover_mean",
}


def _clamp(val: float) -> float:
    return float(np.clip(val, 0.0, 100.0))


def _safe(df: pd.DataFrame, key: str) -> str | None:
    col = _COL.get(key)
    return col if col and col in df.columns else None


def _max_consecutive_wet(series: pd.Series) -> int:
    wet = (series > 0).astype(int).values
    if wet.sum() == 0:
        return 0
    max_run = current = 0
    for w in wet:
        if w:
            current += 1
            max_run = max(max_run, current)
        else:
            current = 0
    return max_run


def _aggregate_stressors(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for base, grp in df.groupby("base_name"):
        g = grp.sort_values("date")

        freeze_thaw = 0
        tc_max, tc_min = _safe(df, "temp_max"), _safe(df, "temp_min")
        if tc_max and tc_min:
            freeze_thaw = int(((g[tc_max] > 32) & (g[tc_min] < 32)).sum())

        tc_prcp  = _safe(df, "precip_sum")
        tc_rain  = _safe(df, "rain_sum")
        tc_snow  = _safe(df, "snowfall_sum")
        tc_ph    = _safe(df, "precip_hours")
        tc_gust  = _safe(df, "wind_gust_max")
        tc_wspd  = _safe(df, "wind_speed_mean")
        tc_hum   = _safe(df, "humidity_max")
        tc_app   = _safe(df, "apparent_temp_max")

        rows.append({
            "base_name":                base,
            "cluster_id":               int(g["cluster_id"].iloc[0]) if "cluster_id" in g.columns else None,
            "freeze_thaw_days":         freeze_thaw,
            "total_precip_mm":          float(g[tc_prcp].sum())           if tc_prcp else 0.0,
            "total_rain_mm":            float(g[tc_rain].sum())           if tc_rain else 0.0,
            "total_snow_cm":            float(g[tc_snow].sum())           if tc_snow else 0.0,
            "total_precip_hours":       float(g[tc_ph].sum())             if tc_ph   else 0.0,
            "max_wind_gust_kmh":        float(g[tc_gust].max())           if tc_gust else 0.0,
            "avg_wind_speed_kmh":       float(g[tc_wspd].mean())          if tc_wspd else 0.0,
            "avg_humidity_max_pct":     float(g[tc_hum].mean())           if tc_hum  else 0.0,
            "max_apparent_temp_f":      float(g[tc_app].max())            if tc_app  else 0.0,
            "avg_temp_swing_f":         float((g[tc_max] - g[tc_min]).mean()) if (tc_max and tc_min) else 0.0,
            "max_consecutive_wet_days": _max_consecutive_wet(g[tc_prcp]) if tc_prcp else 0,
        })
    return pd.DataFrame(rows)


def _normalize_scores(sdf: pd.DataFrame) -> pd.DataFrame:
    out = sdf.copy()
    out["freeze_thaw_score"] = sdf["freeze_thaw_days"].apply(lambda x: _clamp(x / 5 * 100))
    out["rain_score"]        = sdf["total_precip_mm"].apply(lambda x: _clamp(x / 75 * 100))
    out["snow_score"]        = sdf["total_snow_cm"].apply(lambda x: _clamp(x / 25 * 100))
    out["wind_score"]        = sdf["max_wind_gust_kmh"].apply(lambda x: _clamp(max(0.0, x - 20) / 80 * 100))
    out["humidity_score"]    = sdf["avg_humidity_max_pct"].apply(lambda x: _clamp(max(0.0, x - 50) / 45 * 100))
    out["heat_score"]        = sdf["max_apparent_temp_f"].apply(lambda x: _clamp(max(0.0, x - 85) / 25 * 100))
    out["temp_swing_score"]  = sdf["avg_temp_swing_f"].apply(lambda x: _clamp(x / 40 * 100))
    out["wetness_score"]     = sdf["total_precip_hours"].apply(lambda x: _clamp(x / 48 * 100))
    out["wet_streak_score"]  = sdf["max_consecutive_wet_days"].apply(lambda x: _clamp(x / 5 * 100))
    return out


def _compute_system_risks(df: pd.DataFrame) -> pd.DataFrame:
    score_map = {
        "freeze_thaw": "freeze_thaw_score", "rain": "rain_score",
        "snow": "snow_score",               "wind": "wind_score",
        "humidity": "humidity_score",       "heat": "heat_score",
        "temp_swing": "temp_swing_score",   "wetness": "wetness_score",
        "wet_streak": "wet_streak_score",
    }
    out = df.copy()
    for sys_name, weights in _SYSTEM_WEIGHTS.items():
        risk = np.zeros(len(df))
        for component, w in weights.items():
            risk += w * df[score_map[component]].values
        out[f"{sys_name}_risk"] = np.round(risk, 2)
    return out


def _compute_overall_risk(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    overall = np.zeros(len(df))
    for sys_name, w in _OVERALL_WEIGHTS.items():
        overall += w * df[f"{sys_name}_risk"].values
    out["overall_risk"] = np.round(overall, 2)
    return out


def _build_stress_lookup(forecast_path: Path) -> dict[str, float]:
    """Run the full pipeline and return base_name → weather_stress (0-1)."""
    df = pd.read_csv(forecast_path)
    df["date"] = pd.to_datetime(df["date"])

    stressors = _aggregate_stressors(df)
    scored    = _normalize_scores(stressors)
    risked    = _compute_system_risks(scored)
    final     = _compute_overall_risk(risked)

    return dict(zip(final["base_name"], (final["overall_risk"] / 100.0).round(4)))


# Public API
class WeatherStressProvider:
    """Provides per-base weather stress values for the condition index model.

    Loads and caches the full risk pipeline on construction. Subsequent
    calls to get_stress() are O(1) dict lookups.

    Usage:
        provider = WeatherStressProvider()
        stress = provider.get_stress("Eglin Air Force Base")
        model.step(weather_stress=stress, ...)

    For bases not in the forecast dataset, returns the cluster-average
    stress for that base's climate bucket, or a conservative default.
    """

    #: Fallback stress values by cluster when a base has no forecast data.
    _CLUSTER_FALLBACK: dict[int, float] = {
        0: 0.15,   # NORMAL - dry/mild western
        1: 0.25,   # COLD   - cold/wet northeastern
        2: 0.30,   # HOT_HUMID - warm/humid southeastern
    }
    _DEFAULT_FALLBACK: float = 0.20

    def __init__(self, forecast_path: Path | None = None) -> None:
        path = forecast_path or _DEFAULT_FORECAST
        self._lookup: dict[str, float] = _build_stress_lookup(path)

    def get_stress(self, base_name: str, cluster_id: int | None = None) -> float:
        """Return normalized weather stress (0.0 - 1.0) for a base.

        Args:
            base_name:  Installation name matching the forecast dataset.
            cluster_id: Optional climate cluster (0/1/2) used as fallback
                        when the base isn't in the forecast data.

        Returns:
            Float in [0.0, 1.0] where 0 = calm and 1 = extreme stress.
        """
        stress = self._lookup.get(base_name.strip())
        if stress is not None:
            return stress

        # Case-insensitive fallback
        lower = base_name.strip().lower()
        for key, val in self._lookup.items():
            if key.lower() == lower:
                return val

        # Cluster-average fallback
        if cluster_id is not None and cluster_id in self._CLUSTER_FALLBACK:
            return self._CLUSTER_FALLBACK[cluster_id]

        return self._DEFAULT_FALLBACK

    def all_bases(self) -> list[str]:
        """Return the list of base names in the forecast dataset."""
        return list(self._lookup.keys())
