import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

FORECAST_CSV = os.path.join("data", "predictions", "all_bases_7day_forecast.csv")
OUTPUT_DIR = os.path.join("data", "predictions")
PLOT_DIR = "png"

COL = {
    "temp_max": "daily_temperature_2m_max",
    "temp_min": "daily_temperature_2m_min",
    "apparent_temp_max": "daily_apparent_temperature_max",
    "precip_sum": "daily_precipitation_sum",
    "rain_sum": "daily_rain_sum",
    "snowfall_sum": "daily_snowfall_sum",
    "precip_hours": "daily_precipitation_hours",
    "wind_gust_max": "daily_wind_gusts_10m_max",
    "wind_speed_mean": "daily_wind_speed_10m_mean",
    "humidity_max": "daily_relative_humidity_2m_max",
    "cloud_cover": "daily_cloud_cover_mean",
}

SYSTEM_WEIGHTS = {
    "roofing": {
        "wind": 0.30, "rain": 0.25, "freeze_thaw": 0.20,
        "snow": 0.10, "wetness": 0.10, "temp_swing": 0.05,
    },
    "electrical": {
        "humidity": 0.30, "heat": 0.25, "wet_streak": 0.15,
        "rain": 0.15, "wind": 0.10, "temp_swing": 0.05,
    },
    "pavement": {
        "freeze_thaw": 0.30, "temp_swing": 0.25, "rain": 0.20,
        "wetness": 0.10, "snow": 0.10, "wind": 0.05,
    },
    "hvac": {
        "heat": 0.30, "temp_swing": 0.25, "humidity": 0.20,
        "freeze_thaw": 0.15, "wind": 0.10,
    },
    "envelope": {
        "wind": 0.25, "rain": 0.25, "freeze_thaw": 0.20,
        "temp_swing": 0.15, "humidity": 0.10, "snow": 0.05,
    },
    "plumbing": {
        "freeze_thaw": 0.35, "temp_swing": 0.25, "rain": 0.20,
        "humidity": 0.10, "wetness": 0.10,
    },
}

OVERALL_WEIGHTS = {
    "roofing": 0.25, "pavement": 0.20, "electrical": 0.20,
    "hvac": 0.15, "envelope": 0.10, "plumbing": 0.10,
}

SYSTEM_DISPLAY = {
    "roofing": "Roofing",
    "electrical": "Electrical / Controls",
    "pavement": "Pavement / Foundations",
    "hvac": "HVAC / Mechanical",
    "envelope": "Exterior Envelope",
    "plumbing": "Plumbing / Water",
}

CLUSTER_NAMES = {0: "Warm", 1: "Cool", 2: "Cold & Wet"}


def _clamp(val):
    return float(np.clip(val, 0, 100))


def _max_consecutive_wet(precip_series):
    wet = (precip_series > 0).astype(int).values
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


def _safe_col(df, key):
    c = COL.get(key)
    return c if c and c in df.columns else None


def load_forecast():
    if not os.path.exists(FORECAST_CSV):
        raise FileNotFoundError(f"Forecast CSV not found: {FORECAST_CSV}")
    df = pd.read_csv(FORECAST_CSV)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")
    df["date"] = pd.to_datetime(df["date"])
    return df


def aggregate_stressors(df):
    rows = []
    for base, grp in df.groupby("base_name"):
        g = grp.sort_values("date")

        tc_max = _safe_col(df, "temp_max")
        tc_min = _safe_col(df, "temp_min")
        tc_app = _safe_col(df, "apparent_temp_max")
        tc_prcp = _safe_col(df, "precip_sum")
        tc_rain = _safe_col(df, "rain_sum")
        tc_snow = _safe_col(df, "snowfall_sum")
        tc_ph = _safe_col(df, "precip_hours")
        tc_gust = _safe_col(df, "wind_gust_max")
        tc_wspd = _safe_col(df, "wind_speed_mean")
        tc_hum = _safe_col(df, "humidity_max")
        tc_cloud = _safe_col(df, "cloud_cover")

        freeze_thaw = 0
        if tc_max and tc_min:
            freeze_thaw = int(((g[tc_max] > 32) & (g[tc_min] < 32)).sum())

        total_precip = g[tc_prcp].sum() if tc_prcp else 0
        total_rain = g[tc_rain].sum() if tc_rain else 0
        total_snow = g[tc_snow].sum() if tc_snow else 0
        total_precip_hours = g[tc_ph].sum() if tc_ph else 0
        max_gust = g[tc_gust].max() if tc_gust else 0
        avg_wspd = g[tc_wspd].mean() if tc_wspd else 0
        avg_hum_max = g[tc_hum].mean() if tc_hum else 0
        max_app_temp = g[tc_app].max() if tc_app else 0
        avg_swing = (g[tc_max] - g[tc_min]).mean() if (tc_max and tc_min) else 0
        consec_wet = _max_consecutive_wet(g[tc_prcp]) if tc_prcp else 0
        avg_cloud = g[tc_cloud].mean() if tc_cloud else 0

        row = {"base_name": base}
        if "cluster_id" in g.columns:
            row["cluster_id"] = int(g["cluster_id"].iloc[0])
        if "latitude" in g.columns:
            row["latitude"] = round(g["latitude"].iloc[0], 4)
        if "longitude" in g.columns:
            row["longitude"] = round(g["longitude"].iloc[0], 4)

        row.update({
            "forecast_start": g["date"].min().strftime("%Y-%m-%d"),
            "forecast_end": g["date"].max().strftime("%Y-%m-%d"),
            "freeze_thaw_days": freeze_thaw,
            "total_precip_mm": round(float(total_precip), 2),
            "total_rain_mm": round(float(total_rain), 2),
            "total_snow_cm": round(float(total_snow), 2),
            "total_precip_hours": round(float(total_precip_hours), 1),
            "max_wind_gust_kmh": round(float(max_gust), 1),
            "avg_wind_speed_kmh": round(float(avg_wspd), 1),
            "avg_humidity_max_pct": round(float(avg_hum_max), 1),
            "max_apparent_temp_f": round(float(max_app_temp), 1),
            "avg_temp_swing_f": round(float(avg_swing), 1),
            "max_consecutive_wet_days": consec_wet,
            "avg_cloud_cover_pct": round(float(avg_cloud), 1),
        })
        rows.append(row)

    return pd.DataFrame(rows)


def normalize_scores(sdf):
    out = sdf.copy()

    out["freeze_thaw_score"] = sdf["freeze_thaw_days"].apply(
        lambda x: _clamp(x / 5 * 100))
    out["rain_score"] = sdf["total_precip_mm"].apply(
        lambda x: _clamp(x / 75 * 100))
    out["snow_score"] = sdf["total_snow_cm"].apply(
        lambda x: _clamp(x / 25 * 100))
    out["wind_score"] = sdf["max_wind_gust_kmh"].apply(
        lambda x: _clamp(max(0, (x - 20)) / 80 * 100))
    out["humidity_score"] = sdf["avg_humidity_max_pct"].apply(
        lambda x: _clamp(max(0, (x - 50)) / 45 * 100))
    out["heat_score"] = sdf["max_apparent_temp_f"].apply(
        lambda x: _clamp(max(0, (x - 85)) / 25 * 100))
    out["temp_swing_score"] = sdf["avg_temp_swing_f"].apply(
        lambda x: _clamp(x / 40 * 100))
    out["wetness_score"] = sdf["total_precip_hours"].apply(
        lambda x: _clamp(x / 48 * 100))
    out["wet_streak_score"] = sdf["max_consecutive_wet_days"].apply(
        lambda x: _clamp(x / 5 * 100))

    return out


def compute_system_risks(df):
    out = df.copy()
    score_map = {
        "freeze_thaw": "freeze_thaw_score",
        "rain": "rain_score",
        "snow": "snow_score",
        "wind": "wind_score",
        "humidity": "humidity_score",
        "heat": "heat_score",
        "temp_swing": "temp_swing_score",
        "wetness": "wetness_score",
        "wet_streak": "wet_streak_score",
    }

    for sys_name, weights in SYSTEM_WEIGHTS.items():
        risk = np.zeros(len(df))
        for component, w in weights.items():
            risk += w * df[score_map[component]].values
        out[f"{sys_name}_risk"] = np.round(risk, 2)

    return out


def compute_overall_risk(df):
    out = df.copy()

    overall = np.zeros(len(df))
    for sys_name, w in OVERALL_WEIGHTS.items():
        overall += w * df[f"{sys_name}_risk"].values
    out["overall_risk"] = np.round(overall, 2)

    def _band(score):
        if score <= 25:
            return "Low"
        elif score <= 50:
            return "Moderate"
        elif score <= 75:
            return "High"
        return "Critical"

    out["risk_band"] = out["overall_risk"].apply(_band)
    out["midas_weather_multiplier"] = np.round(
        1.0 + (out["overall_risk"] / 100) * 0.5, 4)

    return out


def save_outputs(risk_df):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(PLOT_DIR, exist_ok=True)

    csv_path = os.path.join(OUTPUT_DIR, "degradation_risk_scores.csv")
    risk_df.to_csv(csv_path, index=False)
    print(f"  Saved: {csv_path}")

    xlsx_path = os.path.join(OUTPUT_DIR, "degradation_risk_scores.xlsx")
    risk_df.to_excel(xlsx_path, index=False, engine="openpyxl")
    print(f"  Saved: {xlsx_path}")

    _plot_system_risk_heatmap(risk_df)
    _plot_top_risk_bases(risk_df)
    _plot_component_scores(risk_df)
    if "cluster_id" in risk_df.columns:
        _plot_cluster_risk_comparison(risk_df)

    print(f"\n  All degradation risk charts saved -> {PLOT_DIR}/")


def _plot_system_risk_heatmap(df):
    sys_cols = [f"{s}_risk" for s in SYSTEM_WEIGHTS]
    sys_labels = [SYSTEM_DISPLAY[s] for s in SYSTEM_WEIGHTS]

    pivot = df.set_index("base_name")[sys_cols].copy()
    pivot.columns = sys_labels
    pivot["_avg"] = pivot.mean(axis=1)
    pivot = pivot.sort_values("_avg", ascending=False).drop(columns="_avg")

    h = max(8, len(pivot) * 0.15)
    fig, ax = plt.subplots(figsize=(12, h))
    sns.heatmap(
        pivot, cmap="YlOrRd", ax=ax, linewidths=0,
        vmin=0, vmax=100,
        cbar_kws={"label": "Risk Score (0\u2013100)"},
    )
    ax.set_title("7-Day Degradation Risk by System Type \u2014 All Bases",
                 fontsize=14, fontweight="bold")
    ax.set_ylabel("")
    ax.tick_params(axis="y", labelsize=max(3, min(6, 800 // max(1, len(pivot)))))
    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, "degradation_system_risk_heatmap.png"),
                dpi=150, bbox_inches="tight")
    plt.close()


def _plot_top_risk_bases(df):
    top = df.nlargest(15, "overall_risk")

    band_colors = {
        "Critical": "#DC2626", "High": "#F97316",
        "Moderate": "#EAB308", "Low": "#22C55E",
    }
    colors = [band_colors.get(b, "#94A3B8") for b in top["risk_band"]]

    fig, ax = plt.subplots(figsize=(12, 7))
    bars = ax.barh(
        range(len(top)), top["overall_risk"].values,
        color=colors, edgecolor="white", linewidth=0.5,
    )
    ax.set_yticks(range(len(top)))
    ax.set_yticklabels(top["base_name"].values, fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Overall Infrastructure Risk Score (0\u2013100)", fontsize=11)
    ax.set_title("Top 15 Highest-Risk Bases \u2014 7-Day Forecast",
                 fontsize=14, fontweight="bold")
    ax.set_xlim(0, 105)
    ax.grid(True, alpha=0.3, axis="x")

    for bar, val, band in zip(bars, top["overall_risk"].values, top["risk_band"]):
        ax.text(val + 1, bar.get_y() + bar.get_height() / 2,
                f"{val:.1f}  ({band})", va="center", fontsize=8)

    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, "degradation_top_risk_bases.png"),
                dpi=150, bbox_inches="tight")
    plt.close()


def _plot_component_scores(df):
    score_cols = [
        "freeze_thaw_score", "rain_score", "snow_score",
        "wind_score", "humidity_score", "heat_score",
        "temp_swing_score", "wetness_score", "wet_streak_score",
    ]
    score_labels = [
        "Freeze-Thaw", "Rain", "Snow", "Wind",
        "Humidity", "Heat", "Temp Swing", "Wetness", "Wet Streak",
    ]

    top = df.nlargest(20, "overall_risk")
    pivot = top.set_index("base_name")[score_cols].copy()
    pivot.columns = score_labels

    fig, ax = plt.subplots(figsize=(14, 8))
    sns.heatmap(
        pivot, cmap="YlOrRd", ax=ax, linewidths=0.5,
        vmin=0, vmax=100, annot=True, fmt=".0f",
        cbar_kws={"label": "Component Score (0\u2013100)"},
    )
    ax.set_title("Weather Stress Component Scores \u2014 Top 20 Risk Bases",
                 fontsize=14, fontweight="bold")
    ax.set_ylabel("")
    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, "degradation_component_scores.png"),
                dpi=150, bbox_inches="tight")
    plt.close()


def _plot_cluster_risk_comparison(df):
    sys_names = list(SYSTEM_WEIGHTS.keys())
    sys_cols = [f"{s}_risk" for s in sys_names]
    sys_labels = [SYSTEM_DISPLAY[s] for s in sys_names]

    clusters = sorted(df["cluster_id"].dropna().unique())
    if len(clusters) == 0:
        return

    x = np.arange(len(sys_labels))
    width = 0.8 / len(clusters)
    palette = ["#DC2626", "#2563EB", "#7C3AED", "#22C55E", "#F97316"]

    fig, ax = plt.subplots(figsize=(14, 6))
    for i, cid in enumerate(clusters):
        cdf = df[df["cluster_id"] == cid]
        means = [cdf[col].mean() for col in sys_cols]
        label = CLUSTER_NAMES.get(int(cid), f"Cluster {int(cid)}")
        bars = ax.bar(x + i * width, means, width, label=label,
                      color=palette[i % len(palette)], edgecolor="white")
        for bar, val in zip(bars, means):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    f"{val:.1f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x + width * (len(clusters) - 1) / 2)
    ax.set_xticklabels(sys_labels, fontsize=9, rotation=15, ha="right")
    ax.set_ylabel("Avg Risk Score (0\u2013100)", fontsize=11)
    ax.set_title("Degradation Risk by Cluster \u00d7 System Type",
                 fontsize=14, fontweight="bold")
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3, axis="y")
    ax.set_ylim(0, max(100, ax.get_ylim()[1] + 5))
    plt.tight_layout()
    plt.savefig(os.path.join(PLOT_DIR, "degradation_cluster_risk_comparison.png"),
                dpi=150, bbox_inches="tight")
    plt.close()


def main():
    print("=" * 65)
    print("  DEGRADATION RISK SCORING (Rule-Based MVP)")
    print("=" * 65)

    df = load_forecast()
    n_bases = df["base_name"].nunique()
    print(f"  Loaded {len(df)} forecast rows | {n_bases} bases")
    print(f"  Forecast range: {df['date'].min().date()} -> {df['date'].max().date()}")

    print("\n  Aggregating 7-day weather stressors...")
    stressors = aggregate_stressors(df)

    print("  Normalizing component scores (0\u2013100)...")
    scored = normalize_scores(stressors)

    print("  Computing system-type risk scores...")
    risked = compute_system_risks(scored)

    print("  Computing overall infrastructure risk + bands...")
    final = compute_overall_risk(risked)

    band_counts = final["risk_band"].value_counts()
    print(f"\n  Risk Distribution:")
    for band in ["Critical", "High", "Moderate", "Low"]:
        count = band_counts.get(band, 0)
        print(f"    {band:10s}: {count} bases")

    print(f"\n  Avg overall risk: {final['overall_risk'].mean():.1f}")
    print(f"  Max overall risk: {final['overall_risk'].max():.1f} "
          f"({final.loc[final['overall_risk'].idxmax(), 'base_name']})")

    save_outputs(final)

    print("\n" + "=" * 65)
    print("  DEGRADATION RISK SCORING COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
