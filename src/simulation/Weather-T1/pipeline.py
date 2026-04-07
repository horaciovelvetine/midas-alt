import os
import sys
import glob
import shutil
import argparse
import datetime as dt
import subprocess

ROOT = os.path.dirname(os.path.abspath(__file__))

PIPELINE_STEPS = [
    ("get_airforce_weather_v2.py",            "Fetch current + 7-day forecast",     False),
    ("fetch_air_force_historical_weather.py",  "Fetch 3-year historical daily data", False),
    ("kmeans_weather_clustering.py",           "K-Means clustering",                 True),
    ("individual_base_analysis.py",            "Per-base / per-cluster heatmaps",    True),
    ("af_weather_weekly_model.py",             "Train model + 7-day predictions",    True),
    ("build_degradation_risk.py",              "Degradation risk scoring",           True),
]

OBSOLETE_FILES = [
    "get_military_weather.py",
    "get_military_weather_v2.py",
    "af_weather_seasonal_model.py",
    "midas_config_values(Config).csv",
    "requirements_model.txt",
]

OBSOLETE_DATA_PATTERNS = [
    "air_force_bases_clustered_v2.csv",
    "air_force_cluster_summary_v2.csv",
    "air_force_bases_clustered_k3.csv",
    "air_force_cluster_summary_k3.csv",
    "air_force_bases_weather_v2.csv",
    "air_force_bases_daily_weather_v2.csv",
    "air_force_bases_geocoded_v2.csv",
    "air_force_individual_base_profiles_k3.csv",
    "cluster_bases_by_cluster_k3.txt",
    "cluster_bases_by_cluster.txt",
]

OBSOLETE_PNG_PATTERNS = [
    "air_force_elbow_plot*.png",
    "air_force_cluster_scatter*.png",
    "air_force_cluster_heatmap*.png",
    "air_force_cluster_radar*.png",
    "air_force_cluster_feature_boxplots*.png",
    "air_force_individual_base_heatmap*.png",
    "air_force_cluster_*_heatmap*.png",
    "elbow_plot.png",
]


def _ensure_dirs():
    for d in ("code", "data", "png",
              os.path.join("data", "predictions"),
              os.path.join("data", "models")):
        os.makedirs(os.path.join(ROOT, d), exist_ok=True)


def _resolve_script(name: str) -> str:
    in_code = os.path.join(ROOT, "code", name)
    in_root = os.path.join(ROOT, name)
    if os.path.isfile(in_code):
        return in_code
    if os.path.isfile(in_root):
        return in_root
    return ""


def print_banner():
    today = dt.date.today()
    hist_end = today - dt.timedelta(days=1)
    hist_start = hist_end - dt.timedelta(days=365 * 3)
    forecast_end = today + dt.timedelta(days=7)

    print("=" * 65)
    print("  AIR FORCE WEATHER ANALYSIS PIPELINE")
    print("=" * 65)
    print(f"  Run date            : {today}")
    print(f"  Historical window   : {hist_start}  ->  {hist_end}  (3 years)")
    print(f"  Forecast window     : {today}  ->  {forecast_end}  (7-day)")
    print(f"  ML predictions      : next 7 calendar days")
    print(f"  Base source         : midas_config_values.xlsx")
    print(f"  Output dirs         : data/  png/  code/")
    print("=" * 65)


def migrate_existing_files():
    moved = 0

    for f in glob.glob(os.path.join(ROOT, "air_force_*.csv")):
        dest = os.path.join(ROOT, "data", os.path.basename(f))
        if not os.path.exists(dest):
            shutil.move(f, dest)
            moved += 1

    for f in glob.glob(os.path.join(ROOT, "cluster_bases_*.txt")):
        dest = os.path.join(ROOT, "data", os.path.basename(f))
        if not os.path.exists(dest):
            shutil.move(f, dest)
            moved += 1

    txt_path = os.path.join(ROOT, "air_force_weather_cluster_explanation.txt")
    if os.path.isfile(txt_path):
        dest = os.path.join(ROOT, "data", os.path.basename(txt_path))
        if not os.path.exists(dest):
            shutil.move(txt_path, dest)
            moved += 1

    for f in glob.glob(os.path.join(ROOT, "*.png")):
        dest = os.path.join(ROOT, "png", os.path.basename(f))
        if not os.path.exists(dest):
            shutil.move(f, dest)
            moved += 1

    for old_dir, new_parent in [("predictions", "data"), ("models", "data"), ("plots", "png")]:
        old_path = os.path.join(ROOT, old_dir)
        if os.path.isdir(old_path):
            new_path = os.path.join(ROOT, new_parent, old_dir)
            if os.path.isdir(new_path):
                for item in os.listdir(old_path):
                    src = os.path.join(old_path, item)
                    dst = os.path.join(new_path, item)
                    if not os.path.exists(dst):
                        shutil.move(src, dst)
                        moved += 1
                shutil.rmtree(old_path, ignore_errors=True)
            else:
                shutil.move(old_path, new_path)
                moved += 1

    if moved:
        print(f"  Migrated {moved} file(s) into data/ and png/")


def organise_scripts():
    script_names = [s[0] for s in PIPELINE_STEPS]
    moved = 0
    for name in script_names:
        src = os.path.join(ROOT, name)
        dst = os.path.join(ROOT, "code", name)
        if os.path.isfile(src):
            shutil.move(src, dst)
            moved += 1
    if moved:
        print(f"  Moved {moved} script(s) into code/")


def cleanup():
    print(f"\n{'=' * 65}")
    print("  CLEANUP")
    print(f"{'=' * 65}")
    removed = 0

    for name in OBSOLETE_FILES:
        full = os.path.join(ROOT, name)
        if os.path.isfile(full):
            os.remove(full)
            print(f"  Deleted: {name}")
            removed += 1

    for name in OBSOLETE_DATA_PATTERNS:
        for loc in [ROOT, os.path.join(ROOT, "data")]:
            full = os.path.join(loc, name)
            if os.path.isfile(full):
                os.remove(full)
                print(f"  Deleted: {os.path.relpath(full, ROOT)}")
                removed += 1

    for pattern in OBSOLETE_PNG_PATTERNS:
        for f in glob.glob(os.path.join(ROOT, "png", pattern)):
            os.remove(f)
            print(f"  Deleted: png/{os.path.basename(f)}")
            removed += 1

    for old_era5 in glob.glob(os.path.join(ROOT, "data",
                              "air_force_bases_historical_daily_era5_2016*.csv")):
        os.remove(old_era5)
        print(f"  Deleted: data/{os.path.basename(old_era5)}")
        removed += 1

    for cache_dir in glob.glob(os.path.join(ROOT, "**", "__pycache__"), recursive=True):
        shutil.rmtree(cache_dir, ignore_errors=True)
        removed += 1

    print(f"  Total items removed: {removed}")


def run_step(script_name: str, label: str) -> bool:
    path = _resolve_script(script_name)
    if not path:
        print(f"  SKIP - {script_name} not found")
        return False

    print(f"\n{'\u2500' * 65}")
    print(f"  STEP : {label}")
    print(f"  Script: {os.path.relpath(path, ROOT)}")
    print(f"{'\u2500' * 65}\n")

    result = subprocess.run([sys.executable, path], cwd=ROOT)
    if result.returncode != 0:
        print(f"\n  WARNING: {script_name} exited with code {result.returncode}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="Air Force Weather Pipeline")
    parser.add_argument("--skip-fetch", action="store_true",
                        help="Skip API fetch steps; reuse existing data files")
    parser.add_argument("--cleanup-only", action="store_true",
                        help="Only run cleanup \u2014 no pipeline execution")
    args = parser.parse_args()

    _ensure_dirs()
    print_banner()

    migrate_existing_files()

    if args.cleanup_only:
        cleanup()
        organise_scripts()
        print("\nCleanup complete.")
        return

    for script_name, label, skip_safe in PIPELINE_STEPS:
        if args.skip_fetch and not skip_safe:
            print(f"\n  SKIP (--skip-fetch): {label}")
            continue

        ok = run_step(script_name, label)
        if not ok:
            print(f"\n  Pipeline stopped at: {label}")
            print("  Fix the issue and re-run, or use --skip-fetch to bypass API steps.")
            sys.exit(1)

    cleanup()
    organise_scripts()

    print("\n" + "=" * 65)
    print("  PIPELINE COMPLETE")
    print("=" * 65)
    print("  Output directories:")
    print("    data/              - CSV data, cluster labels")
    print("    data/predictions/  - 7-day forecasts + degradation risk scores")
    print("    data/models/       - Trained XGBoost model (.joblib)")
    print("    png/               - All charts, heatmaps, forecast + risk plots")
    print("    code/              - Python pipeline scripts")
    print("=" * 65)


if __name__ == "__main__":
    main()
