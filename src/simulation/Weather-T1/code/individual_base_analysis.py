import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
from sklearn.preprocessing import StandardScaler
import warnings
warnings.filterwarnings("ignore")

CLUSTERED_CSV = os.path.join("data", "bases_with_cluster_labels.csv")
CLUSTERED_CSV_FALLBACK = os.path.join("data", "air_force_bases_clustered_k3.csv")

CURRENT_FEATURES = [
    "current_temperature_2m", "current_relative_humidity_2m",
    "current_apparent_temperature", "current_precipitation",
    "current_rain", "current_snowfall", "current_weather_code",
    "current_cloud_cover", "current_pressure_msl", "current_surface_pressure",
    "current_wind_speed_10m", "current_wind_direction_10m", "current_wind_gusts_10m",
]

SHORT_LABELS = {
    "current_temperature_2m": "Temp (\u00b0F)",
    "current_relative_humidity_2m": "Humidity (%)",
    "current_apparent_temperature": "Feels Like (\u00b0F)",
    "current_precipitation": "Precip (mm)",
    "current_rain": "Rain (mm)",
    "current_snowfall": "Snow (mm)",
    "current_weather_code": "Weather Code",
    "current_cloud_cover": "Cloud Cover (%)",
    "current_pressure_msl": "Pressure MSL",
    "current_surface_pressure": "Surface Press.",
    "current_wind_speed_10m": "Wind Speed (km/h)",
    "current_wind_direction_10m": "Wind Dir (\u00b0)",
    "current_wind_gusts_10m": "Wind Gusts (km/h)",
}

CLUSTER_NAMES = {
    0: "Warm",
    1: "Cool",
    2: "Cold and Wet (Rain/Snow)",
}

CLUSTER_FILE_LABELS = {
    0: "warm",
    1: "cool",
    2: "cold_wet",
}


def main():
    for d in ("data", "png"):
        os.makedirs(d, exist_ok=True)

    clustered_path = CLUSTERED_CSV
    if not os.path.exists(clustered_path):
        clustered_path = CLUSTERED_CSV_FALLBACK

    print("  Loading clustered data...")
    df = pd.read_csv(clustered_path)

    daily_cols = [c for c in df.columns if "7day_avg" in c]
    ALL_FEATURES = [c for c in CURRENT_FEATURES if c in df.columns] + daily_cols

    labels = dict(SHORT_LABELS)
    for c in daily_cols:
        short = c.replace("daily_", "").replace("_7day_avg", "").replace("_", " ").title()
        labels[c] = f"{short} (7d)"

    X = df[ALL_FEATURES].copy()
    X = X.fillna(X.median())
    scaler = StandardScaler()
    X_scaled = pd.DataFrame(scaler.fit_transform(X), columns=ALL_FEATURES, index=df.index)

    df_sorted = df.copy()
    df_sorted["_sort_temp"] = X_scaled["current_temperature_2m"]
    df_sorted = df_sorted.sort_values(["Cluster", "_sort_temp"], ascending=[True, False])
    X_sorted = X_scaled.loc[df_sorted.index]

    short_cols = [labels.get(c, c) for c in ALL_FEATURES]

    print("  Generating heatmaps...")
    fig, ax = plt.subplots(figsize=(20, 40))
    plot_data = X_sorted.copy()
    plot_data.columns = short_cols
    y_labels = [
        f"{row['Site_Name']} ({str(row['State']).upper()})"
        for _, row in df_sorted.iterrows()
    ]

    sns.heatmap(
        plot_data, ax=ax, cmap="RdYlBu_r", center=0,
        yticklabels=y_labels, xticklabels=short_cols,
        vmin=-3, vmax=3, linewidths=0,
        cbar_kws={"label": "Standardized Value (Z-score)", "shrink": 0.3},
    )
    ax.set_title(
        "All Air Force Bases \u2014 Individual Weather Profiles\n"
        "(Sorted by Cluster, then Temperature)",
        fontsize=16, fontweight="bold", pad=20,
    )
    ax.tick_params(axis="y", labelsize=3)
    ax.tick_params(axis="x", labelsize=8, rotation=45)

    cluster_counts = df_sorted["Cluster"].value_counts().sort_index()
    cumsum = 0
    for cl in sorted(cluster_counts.index):
        count = cluster_counts[cl]
        mid = cumsum + count / 2
        cname = CLUSTER_NAMES.get(cl, f"Cluster {cl}")
        ax.text(
            -1.5, mid, f"Cluster {cl}: {cname}",
            fontsize=10, fontweight="bold", ha="right", va="center",
            color=["#d32f2f", "#1565c0", "#6a1b9a"][cl % 3],
        )
        cumsum += count
        if cl < max(cluster_counts.index):
            ax.axhline(y=cumsum, color="black", linewidth=2)

    plt.tight_layout()
    heatmap_path = os.path.join("png", "all_bases_weather_heatmap.png")
    fig.savefig(heatmap_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {heatmap_path}")

    for cl in sorted(df["Cluster"].unique()):
        mask = df_sorted["Cluster"] == cl
        cl_data = X_sorted.loc[mask].copy()
        cl_df = df_sorted.loc[mask]

        n = len(cl_data)
        fig_h = max(8, n * 0.12 + 3)
        fig, ax = plt.subplots(figsize=(18, fig_h))

        cl_plot = cl_data.copy()
        cl_plot.columns = short_cols
        y_labels_cl = [
            f"{row['Site_Name']} ({str(row['State']).upper()})"
            for _, row in cl_df.iterrows()
        ]

        sns.heatmap(
            cl_plot, ax=ax, cmap="RdYlBu_r", center=0,
            yticklabels=y_labels_cl, xticklabels=short_cols,
            vmin=-3, vmax=3, linewidths=0.1,
            cbar_kws={"label": "Standardized Z-score", "shrink": 0.5},
        )
        cname = CLUSTER_NAMES.get(cl, f"Cluster {cl}")
        ax.set_title(
            f"Cluster {cl}: {cname} \u2014 {n} Bases (Individual Weather Profiles)",
            fontsize=14, fontweight="bold", pad=15,
        )
        ax.tick_params(axis="y", labelsize=5 if n > 100 else 7)
        ax.tick_params(axis="x", labelsize=8, rotation=45)

        plt.tight_layout()
        flabel = CLUSTER_FILE_LABELS.get(cl, str(cl))
        fname = os.path.join("png", f"cluster_{cl}_{flabel}_bases_heatmap.png")
        fig.savefig(fname, dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {fname}  ({n} bases)")

    print("  Generating base profiles...")
    profiles = df_sorted[
        ["OBJECTID", "Site_Name", "State", "latitude", "longitude", "Cluster"]
    ].copy()

    for feat in ALL_FEATURES:
        short = labels.get(feat, feat)
        profiles[short] = df_sorted[feat].values

    for feat in ALL_FEATURES:
        short = labels.get(feat, feat)
        profiles[f"{short} (z-score)"] = X_sorted[feat].values

    for feat in ALL_FEATURES:
        short = labels.get(feat, feat)
        profiles[f"{short} (rank)"] = (
            df[feat]
            .rank(ascending=False, method="min")
            .loc[df_sorted.index]
            .astype(int)
            .values
        )

    profiles_path = os.path.join("data", "individual_base_weather_profiles.csv")
    profiles.to_csv(profiles_path, index=False)
    print(f"  Saved: {profiles_path}")

    print("\n" + "=" * 65)
    print("  AIR FORCE INDIVIDUAL BASE ANALYSIS COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
