import os
import glob
import warnings
import datetime as dt

import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
import joblib
from tqdm import tqdm
from sklearn.multioutput import MultiOutputRegressor
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import (
    mean_absolute_error, mean_squared_error, r2_score,
    accuracy_score, f1_score,
)
from sklearn.preprocessing import LabelEncoder
from xgboost import XGBRegressor, XGBClassifier

warnings.filterwarnings("ignore")

CONFIG = {
    "era5_glob": os.path.join("data", "air_force_bases_historical_daily_era5_*.csv"),
    "clustered_file": os.path.join("data", "bases_with_cluster_labels.csv"),
    "clustered_file_fallback": os.path.join("data", "air_force_bases_clustered_k3.csv"),
    "geocoded_file": os.path.join("data", "base_locations.csv"),
    "geocoded_file_fallback": os.path.join("data", "air_force_bases_geocoded_v2.csv"),
    "output_predictions": os.path.join("data", "predictions"),
    "output_models": os.path.join("data", "models"),
    "output_plots": "png",
    "forecast_days": 7,
    "historical_min_years": 0.8,
    "historical_min_bases": 40,
    "min_days_required": 90,
    "xgb_params": {
        "n_estimators": 200,
        "max_depth": 5,
        "learning_rate": 0.05,
        "subsample": 0.85,
        "colsample_bytree": 0.85,
        "min_child_weight": 3,
        "gamma": 0.1,
        "reg_alpha": 0.1,
        "reg_lambda": 1.0,
        "random_state": 42,
        "verbosity": 0,
        "n_jobs": -1,
    },
}

NON_WEATHER_COLS = {
    "date", "base_name", "cluster_id",
    "latitude", "longitude", "year", "month", "day",
    "dayofyear", "dayofweek",
    "state", "reporting_component", "site_name",
    "objectid", "id", "index",
    "daily_sunrise", "daily_sunset",
    "latitude_x", "latitude_y", "longitude_x", "longitude_y",
}

WEATHER_KEYWORDS = [
    "temperature", "temp", "precip", "rain", "wind", "pressure",
    "humidity", "dewpoint", "dew_point", "radiation", "cloud",
    "snow", "evapot", "solar", "daylight", "sunshine",
    "weather_code", "apparent",
]

CLUSTER_LABELS = {0: "warm", 1: "cool", 2: "cold_wet"}
CLUSTER_NAMES = {0: "Warm", 1: "Cool", 2: "Cold & Wet"}

PRECIP_TARGET_KEYWORDS = ["precipitation_sum", "rain_sum", "snowfall_sum"]
WIND_DIR_TARGET_KEYWORDS = ["wind_direction"]
WEATHER_CODE_TARGET_KEYWORDS = ["weather_code"]


def _is_precip_target(v):
    return any(kw in v for kw in PRECIP_TARGET_KEYWORDS)


def _is_wind_dir_target(v):
    return any(kw in v for kw in WIND_DIR_TARGET_KEYWORDS)


def _is_weather_code_target(v):
    return any(kw in v for kw in WEATHER_CODE_TARGET_KEYWORDS)


def _categorize_vars(weather_vars):
    wc = [v for v in weather_vars if _is_weather_code_target(v)]
    wd = [v for v in weather_vars if _is_wind_dir_target(v)]
    precip = [v for v in weather_vars if _is_precip_target(v)]
    regular = [v for v in weather_vars if v not in wc + wd + precip]
    return {"weather_code": wc, "wind_dir": wd, "precip": precip, "regular": regular}


def _resolve_file(primary, fallback):
    if os.path.exists(primary):
        return primary
    if os.path.exists(fallback):
        return fallback
    return None


def resolve_historical_file():
    matches = sorted(
        glob.glob(CONFIG["era5_glob"]),
        key=os.path.getmtime, reverse=True,
    )
    if matches:
        return matches[0]
    raise FileNotFoundError("No historical daily CSV found matching pattern.")


def load_data():
    print("\n  Loading historical daily data...")
    f = resolve_historical_file()
    df = pd.read_csv(f)
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    date_col = next((c for c in df.columns if "date" in c), None)
    if not date_col:
        raise ValueError("No date column found.")
    df[date_col] = pd.to_datetime(df[date_col])
    df = df.rename(columns={date_col: "date"})

    name_col = next(
        (c for c in df.columns if c in ("site_name", "base_name") or "site" in c),
        None,
    )
    if not name_col:
        raise ValueError("No base name column found.")
    df = df.rename(columns={name_col: "base_name"})

    for bad in ["latitude_x", "latitude_y", "longitude_x", "longitude_y"]:
        if bad in df.columns:
            df = df.drop(columns=[bad])

    cpath = _resolve_file(CONFIG["clustered_file"], CONFIG["clustered_file_fallback"])
    if cpath:
        try:
            cl = pd.read_csv(cpath)
            cl.columns = cl.columns.str.strip().str.lower().str.replace(" ", "_")
            key = next((c for c in cl.columns if "site" in c or "base" in c), None)
            if key:
                cl = cl.rename(columns={key: "base_name"})
                ccol = next((c for c in cl.columns if "cluster" in c), None)
                if ccol:
                    cl = cl[["base_name", ccol]].drop_duplicates("base_name")
                    df = df.merge(cl, on="base_name", how="left")
                    df = df.rename(columns={ccol: "cluster_id"})
        except Exception:
            pass

    if "latitude" not in df.columns:
        gpath = _resolve_file(CONFIG["geocoded_file"], CONFIG["geocoded_file_fallback"])
        if gpath:
            try:
                geo = pd.read_csv(gpath)
                geo.columns = geo.columns.str.strip().str.lower().str.replace(" ", "_")
                key = next((c for c in geo.columns if "site" in c or "base" in c), None)
                if key:
                    geo = geo.rename(columns={key: "base_name"})
                    lat = next((c for c in geo.columns if "lat" in c), None)
                    lon = next((c for c in geo.columns if "lon" in c), None)
                    if lat and lon:
                        geo = geo[["base_name", lat, lon]].drop_duplicates("base_name")
                        geo = geo.rename(columns={lat: "latitude", lon: "longitude"})
                        df = df.merge(geo, on="base_name", how="left")
            except Exception:
                pass

    n_bases = df["base_name"].nunique()
    span = (df["date"].max() - df["date"].min()).days
    print(f"    {len(df):,} rows | {n_bases} bases | "
          f"{df['date'].min().date()} -> {df['date'].max().date()} ({span / 365.25:.1f}y)")

    if span < int(CONFIG["historical_min_years"] * 365):
        raise ValueError(f"Need >= {CONFIG['historical_min_years']} years of data.")
    if n_bases < CONFIG["historical_min_bases"]:
        raise ValueError(f"Only {n_bases} bases; need >= {CONFIG['historical_min_bases']}.")

    return df


def detect_weather_variables(df):
    cols = [
        c for c in df.columns
        if c not in NON_WEATHER_COLS
        and pd.api.types.is_numeric_dtype(df[c])
        and any(kw in c for kw in WEATHER_KEYWORDS)
    ]
    print(f"  Detected {len(cols)} weather variables")
    return cols


def engineer_daily_features(daily_base, weather_vars):
    df = daily_base.sort_values("date").copy().reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    n = len(df)

    df["doy_sin"] = np.sin(2 * np.pi * df["date"].dt.dayofyear / 365.25)
    df["doy_cos"] = np.cos(2 * np.pi * df["date"].dt.dayofyear / 365.25)
    df["month_sin"] = np.sin(2 * np.pi * df["date"].dt.month / 12)
    df["month_cos"] = np.cos(2 * np.pi * df["date"].dt.month / 12)
    df["dow"] = df["date"].dt.dayofweek
    df["trend"] = np.arange(n)

    for var in weather_vars:
        if var not in df.columns:
            continue
        v = df[var]

        for lag in [1, 7, 14]:
            if n > lag:
                df[f"{var}_lag{lag}"] = v.shift(lag)
        if n > 7:
            df[f"{var}_roll7"] = v.shift(1).rolling(7, min_periods=3).mean()

        if _is_wind_dir_target(var):
            rad = np.deg2rad(v)
            df[f"{var}_sin"] = np.sin(rad)
            df[f"{var}_cos"] = np.cos(rad)
            for lag in [1, 7]:
                if n > lag:
                    df[f"{var}_sin_lag{lag}"] = df[f"{var}_sin"].shift(lag)
                    df[f"{var}_cos_lag{lag}"] = df[f"{var}_cos"].shift(lag)

        if _is_precip_target(var):
            df[f"{var}_flag"] = (v > 0).astype(int)
            if n > 1:
                df[f"{var}_flag_lag1"] = df[f"{var}_flag"].shift(1)
            if n > 3:
                df[f"{var}_roll3"] = v.shift(1).rolling(3, min_periods=1).mean()
            if n > 14:
                df[f"{var}_roll14"] = v.shift(1).rolling(14, min_periods=3).mean()

    if "cluster_id" in df.columns:
        df["cluster_id"] = df["cluster_id"].fillna(-1).astype(int)
        dummies = pd.get_dummies(df["cluster_id"], prefix="cl")
        df = pd.concat([df, dummies], axis=1)

    lag1_cols = [c for c in df.columns if c.endswith("_lag1")]
    if lag1_cols:
        df = df.dropna(subset=lag1_cols).reset_index(drop=True)

    return df


def get_feature_cols(df, weather_vars):
    exclude = set(weather_vars) | NON_WEATHER_COLS
    return [
        c for c in df.columns
        if c not in exclude and pd.api.types.is_numeric_dtype(df[c])
    ]


def _build_reg_targets(df, weather_vars, cats):
    reg_target_cols = []
    orig_var_map = {}
    Y = pd.DataFrame(index=df.index)

    for v in cats["regular"]:
        Y[v] = df[v].fillna(0)
        reg_target_cols.append(v)
        orig_var_map[v] = (v, "none")

    for v in cats["precip"]:
        Y[v] = np.log1p(df[v].clip(lower=0).fillna(0))
        reg_target_cols.append(v)
        orig_var_map[v] = (v, "log1p")

    for v in cats["wind_dir"]:
        sin_col = f"{v}__tgt_sin"
        cos_col = f"{v}__tgt_cos"
        rad = np.deg2rad(df[v].fillna(0))
        Y[sin_col] = np.sin(rad)
        Y[cos_col] = np.cos(rad)
        reg_target_cols.extend([sin_col, cos_col])
        orig_var_map[sin_col] = (v, "wind_sin")
        orig_var_map[cos_col] = (v, "wind_cos")

    return Y, reg_target_cols, orig_var_map


def _inverse_predict_row(reg_preds, reg_target_cols, orig_var_map,
                         wc_pred, wc_var, label_encoder):
    result = {}
    wind_parts = {}

    for j, col in enumerate(reg_target_cols):
        orig_var, transform = orig_var_map[col]
        val = float(reg_preds[j])
        if transform == "none":
            result[orig_var] = val
        elif transform == "log1p":
            result[orig_var] = max(0.0, np.expm1(val))
        elif transform == "wind_sin":
            wind_parts.setdefault(orig_var, {})["sin"] = val
        elif transform == "wind_cos":
            wind_parts.setdefault(orig_var, {})["cos"] = val

    for orig_var, parts in wind_parts.items():
        result[orig_var] = float(np.rad2deg(
            np.arctan2(parts["sin"], parts["cos"])
        ) % 360)

    if wc_var is not None and wc_pred is not None:
        decoded = label_encoder.inverse_transform([int(wc_pred)])[0]
        result[wc_var] = int(decoded)

    return result


def train_unified_model(daily_df, weather_vars):
    print(f"\n  Building feature matrix ({len(weather_vars)} targets)...")
    pieces = []
    min_days = CONFIG["min_days_required"]

    for base, grp in tqdm(daily_df.groupby("base_name"), desc="  Feature eng.", leave=False):
        if len(grp) < min_days:
            continue
        try:
            feat = engineer_daily_features(grp, weather_vars)
            feat["base_name"] = base
            pieces.append(feat)
        except Exception:
            continue

    if not pieces:
        raise ValueError("No bases with enough data for training.")

    df = pd.concat(pieces, ignore_index=True)

    geo = daily_df.drop_duplicates("base_name").set_index("base_name")[
        [c for c in ["latitude", "longitude"] if c in daily_df.columns]
    ]
    if not geo.empty:
        df = df.merge(geo, on="base_name", how="left", suffixes=("", "_geo"))

    feature_cols = get_feature_cols(df, weather_vars)
    for gc in ["latitude", "longitude"]:
        if gc in df.columns and gc not in feature_cols:
            feature_cols.append(gc)

    X = df[feature_cols].fillna(0)

    cats = _categorize_vars(weather_vars)
    Y_reg, reg_target_cols, orig_var_map = _build_reg_targets(df, weather_vars, cats)

    wc_var = cats["weather_code"][0] if cats["weather_code"] else None
    le = None
    y_wc_enc = None
    if wc_var:
        le = LabelEncoder()
        y_wc_enc = le.fit_transform(df[wc_var].fillna(0).astype(int))

    print(f"    {len(X):,} samples | {len(feature_cols)} features | "
          f"{len(reg_target_cols)} reg targets"
          + (f" | 1 classifier target ({len(le.classes_)} classes)" if le else ""))

    max_folds = min(3, max(2, len(X) // 1000))
    tscv = TimeSeriesSplit(n_splits=max_folds)

    cv_reg = {v: {"mae": [], "rmse": [], "r2": []}
              for v in weather_vars if v != wc_var}
    cv_cls = {"accuracy": [], "f1": []} if wc_var else None

    print(f"    Cross-validating ({max_folds} folds)...")
    for tr, va in tscv.split(X):
        Xtr, Xva = X.iloc[tr], X.iloc[va]

        reg_m = MultiOutputRegressor(XGBRegressor(**CONFIG["xgb_params"]))
        reg_m.fit(Xtr, Y_reg.iloc[tr])
        reg_preds = reg_m.predict(Xva)

        wind_sin_p = {}
        wind_cos_p = {}
        for j, col in enumerate(reg_target_cols):
            orig_var, transform = orig_var_map[col]
            yp = reg_preds[:, j]

            if transform == "wind_sin":
                wind_sin_p[orig_var] = yp
                continue
            if transform == "wind_cos":
                wind_cos_p[orig_var] = yp
                continue

            yt_orig = df[orig_var].iloc[va].values
            if transform == "log1p":
                yp_orig = np.maximum(0, np.expm1(yp))
            else:
                yp_orig = yp

            cv_reg[orig_var]["mae"].append(mean_absolute_error(yt_orig, yp_orig))
            cv_reg[orig_var]["rmse"].append(np.sqrt(mean_squared_error(yt_orig, yp_orig)))
            cv_reg[orig_var]["r2"].append(
                r2_score(yt_orig, yp_orig) if len(yt_orig) > 1 else 0
            )

        for wdv in cats["wind_dir"]:
            pred_angles = np.rad2deg(
                np.arctan2(wind_sin_p[wdv], wind_cos_p[wdv])
            ) % 360
            true_angles = df[wdv].iloc[va].values
            diff = np.abs(pred_angles - true_angles)
            circ_diff = np.minimum(diff, 360 - diff)
            cv_reg[wdv]["mae"].append(float(np.mean(circ_diff)))
            cv_reg[wdv]["rmse"].append(float(np.sqrt(np.mean(circ_diff ** 2))))
            total_var = np.var(true_angles)
            cv_reg[wdv]["r2"].append(
                float(1 - np.mean(circ_diff ** 2) / total_var) if total_var > 0 else 0
            )

        if wc_var and le is not None:
            n_cls = len(le.classes_)
            cls_params = {**CONFIG["xgb_params"],
                          "objective": "multi:softmax", "num_class": n_cls}
            cls_m = XGBClassifier(**cls_params)
            cls_m.fit(Xtr, y_wc_enc[tr])
            wc_p = cls_m.predict(Xva)
            cv_cls["accuracy"].append(accuracy_score(y_wc_enc[va], wc_p))
            cv_cls["f1"].append(f1_score(y_wc_enc[va], wc_p,
                                         average="weighted", zero_division=0))

    print("    Training final models...")
    final_reg = MultiOutputRegressor(XGBRegressor(**CONFIG["xgb_params"]))
    final_reg.fit(X, Y_reg)

    final_cls = None
    if wc_var and le is not None:
        n_cls = len(le.classes_)
        cls_params = {**CONFIG["xgb_params"],
                      "objective": "multi:softmax", "num_class": n_cls}
        final_cls = XGBClassifier(**cls_params)
        final_cls.fit(X, y_wc_enc)

    metrics = []
    for v in weather_vars:
        if v == wc_var:
            metrics.append({
                "variable": v,
                "cv_accuracy": round(np.mean(cv_cls["accuracy"]), 4),
                "cv_f1": round(np.mean(cv_cls["f1"]), 4),
                "cv_mae": None, "cv_rmse": None, "cv_r2": None,
                "n_samples": len(X), "n_features": len(feature_cols),
                "model_type": "classifier",
            })
        else:
            m = cv_reg[v]
            metrics.append({
                "variable": v,
                "cv_mae": round(np.mean(m["mae"]), 4),
                "cv_rmse": round(np.mean(m["rmse"]), 4),
                "cv_r2": round(np.mean(m["r2"]), 4),
                "cv_accuracy": None, "cv_f1": None,
                "n_samples": len(X), "n_features": len(feature_cols),
                "model_type": "regressor",
            })

    bundle = {
        "reg_model": final_reg,
        "cls_model": final_cls,
        "feature_cols": feature_cols,
        "reg_target_cols": reg_target_cols,
        "orig_var_map": orig_var_map,
        "wc_var": wc_var,
        "label_encoder": le,
        "cats": cats,
    }

    return bundle, metrics


def predict_7days(daily_df, bundle, weather_vars):
    n_days = CONFIG["forecast_days"]
    print(f"\n  Predicting next {n_days} days for each base...")

    reg_model = bundle["reg_model"]
    cls_model = bundle["cls_model"]
    feature_cols = bundle["feature_cols"]
    reg_target_cols = bundle["reg_target_cols"]
    orig_var_map = bundle["orig_var_map"]
    wc_var = bundle["wc_var"]
    le = bundle["label_encoder"]

    all_rows = []
    min_days = CONFIG["min_days_required"]

    for base in tqdm(daily_df["base_name"].unique(), desc="  Forecasting", leave=False):
        hist = daily_df[daily_df["base_name"] == base].sort_values("date").copy()
        if len(hist) < min_days:
            continue

        last_date = hist["date"].max()
        extended = hist.copy()

        static = {}
        for sc in ["cluster_id", "latitude", "longitude"]:
            if sc in hist.columns:
                val = hist[sc].dropna()
                static[sc] = val.iloc[0] if len(val) > 0 else np.nan

        for d in range(1, n_days + 1):
            fdate = last_date + pd.Timedelta(days=d)
            placeholder = {c: np.nan for c in extended.columns}
            placeholder.update({"base_name": base, "date": fdate})
            placeholder.update(static)
            for v in weather_vars:
                placeholder[v] = np.nan

            ext_tmp = pd.concat(
                [extended, pd.DataFrame([placeholder])], ignore_index=True
            )

            try:
                feat = engineer_daily_features(ext_tmp, weather_vars)
                lr = feat.iloc[[-1]]
                avail = [c for c in feature_cols if c in lr.columns]
                missing = [c for c in feature_cols if c not in lr.columns]
                X_pred = lr[avail].fillna(0).copy()
                for mc in missing:
                    X_pred[mc] = 0
                X_pred = X_pred[feature_cols]

                reg_preds = reg_model.predict(X_pred)[0]

                wc_pred = None
                if cls_model is not None:
                    wc_pred = cls_model.predict(X_pred)[0]

                result = _inverse_predict_row(
                    reg_preds, reg_target_cols, orig_var_map,
                    wc_pred, wc_var, le,
                )
            except Exception:
                result = {v: np.nan for v in weather_vars}

            row = {"base_name": base, "date": fdate}
            row.update(static)
            for v in weather_vars:
                row[v] = float(result.get(v, 0.0))

            extended = pd.concat(
                [extended, pd.DataFrame([row])], ignore_index=True
            )
            all_rows.append(row)

    if not all_rows:
        return pd.DataFrame(columns=["base_name", "date"] + weather_vars)

    return pd.DataFrame(all_rows)


def _nice_col(c):
    return (
        c.replace("daily_", "")
        .replace("_", " ")
        .title()
        .replace("2M", "2m")
        .replace("10M", "10m")
    )


def save_outputs(forecast_df, bundle, metrics, daily_df, weather_vars):
    for d in [CONFIG["output_predictions"], CONFIG["output_models"], CONFIG["output_plots"]]:
        os.makedirs(d, exist_ok=True)

    pred_dir = CONFIG["output_predictions"]
    plot_dir = CONFIG["output_plots"]

    if not forecast_df.empty:
        nice = forecast_df.copy()
        nice.columns = [_nice_col(c) if c in weather_vars else c for c in nice.columns]

        xlsx = os.path.join(pred_dir, "all_bases_7day_forecast.xlsx")
        nice.to_excel(xlsx, index=False, engine="openpyxl")
        print(f"\n  Saved: {xlsx}")

        csv = os.path.join(pred_dir, "all_bases_7day_forecast.csv")
        forecast_df.to_csv(csv, index=False)

    if not forecast_df.empty and "cluster_id" in forecast_df.columns:
        for cid in sorted(forecast_df["cluster_id"].dropna().unique()):
            ci = int(cid)
            cdf = forecast_df[forecast_df["cluster_id"] == cid]
            label = CLUSTER_LABELS.get(ci, str(ci))
            name = CLUSTER_NAMES.get(ci, f"Cluster {ci}")

            nice = cdf.copy()
            nice.columns = [_nice_col(c) if c in weather_vars else c for c in nice.columns]
            out = os.path.join(pred_dir, f"cluster_{ci}_{label}_7day_forecast.xlsx")
            nice.to_excel(out, index=False, engine="openpyxl")
            print(f"  Saved: {out}  ({cdf['base_name'].nunique()} bases \u2014 {name})")

    reg_model = bundle["reg_model"]
    feature_cols = bundle["feature_cols"]

    mpath = os.path.join(CONFIG["output_models"], "7day_weather_model.joblib")
    joblib.dump({
        "reg_model": bundle["reg_model"],
        "cls_model": bundle["cls_model"],
        "feature_cols": feature_cols,
        "reg_target_cols": bundle["reg_target_cols"],
        "orig_var_map": bundle["orig_var_map"],
        "wc_var": bundle["wc_var"],
        "label_encoder": bundle["label_encoder"],
        "weather_vars": weather_vars,
        "created": dt.datetime.now().isoformat(),
    }, mpath)
    print(f"  Saved: {mpath}")

    if metrics:
        mdf = pd.DataFrame(metrics)
        mdf.to_csv(os.path.join(pred_dir, "model_metrics.csv"), index=False)

        reg_m = mdf[mdf["model_type"] == "regressor"].dropna(subset=["cv_r2"])
        if not reg_m.empty:
            top = reg_m.nlargest(10, "cv_r2")
            print(f"\n  Regressor Performance (top 10 by R\u00b2):")
            print(top[["variable", "cv_mae", "cv_r2"]].to_string(index=False))

        cls_m = mdf[mdf["model_type"] == "classifier"]
        if not cls_m.empty:
            print(f"\n  Classifier Performance:")
            print(cls_m[["variable", "cv_accuracy", "cv_f1"]].to_string(index=False))

    if forecast_df.empty:
        return

    sample_bases = forecast_df["base_name"].unique()[:4]
    key_vars = [v for v in weather_vars if not _is_weather_code_target(v)][:6]

    for var in key_vars:
        if var not in forecast_df.columns:
            continue
        n_bases_plot = min(len(sample_bases), 4)
        fig, axes = plt.subplots(2, 2, figsize=(16, 10))
        nice_var = _nice_col(var)
        fig.suptitle(f"7-Day Forecast: {nice_var}", fontsize=14, fontweight="bold")

        for i in range(4):
            ax = axes.flatten()[i]
            if i < n_bases_plot:
                base = sample_bases[i]

                pred = forecast_df[forecast_df["base_name"] == base][["date", var]]
                pred["date"] = pd.to_datetime(pred["date"])

                hist = daily_df[daily_df["base_name"] == base][["date", var]].dropna()
                hist["date"] = pd.to_datetime(hist["date"])
                hist = hist.sort_values("date")
                if len(pred) > 0:
                    cutoff = pred["date"].min() - pd.Timedelta(days=30)
                    hist = hist[hist["date"] >= cutoff]

                ax.plot(hist["date"], hist[var], color="#2563EB", lw=1.5, label="Last 30 days")
                ax.plot(pred["date"], pred[var], color="#DC2626", lw=2.5, ls="--",
                        marker="o", ms=5, label="7-Day Forecast")
                if len(pred) > 0:
                    ax.axvspan(pred["date"].min(), pred["date"].max(),
                               color="#FEE2E2", alpha=0.3)
                ax.set_title(base, fontsize=9, fontweight="bold")
                ax.legend(fontsize=8)
                ax.grid(True, alpha=0.3)
                ax.tick_params(axis="x", rotation=30, labelsize=7)
            else:
                ax.set_visible(False)

        plt.tight_layout()
        safe_name = var.replace("daily_", "")
        plt.savefig(os.path.join(plot_dir, f"7day_forecast_{safe_name}.png"),
                    dpi=150, bbox_inches="tight")
        plt.close()

    temp_var = next((v for v in weather_vars if "temperature_2m_mean" in v), None)
    if not temp_var:
        temp_var = next((v for v in weather_vars if "temperature_2m_max" in v), None)

    if temp_var and temp_var in forecast_df.columns:
        pivot = forecast_df.pivot_table(
            index="base_name", columns="date", values=temp_var
        )
        pivot.columns = [pd.to_datetime(c).strftime("%b %d") for c in pivot.columns]

        if "cluster_id" in forecast_df.columns:
            cluster_map = (
                forecast_df.drop_duplicates("base_name")
                .set_index("base_name")["cluster_id"]
            )
            pivot["_cl"] = pivot.index.map(cluster_map)
            pivot = pivot.sort_values("_cl").drop(columns="_cl")

        h = max(8, len(pivot) * 0.15)
        fig, ax = plt.subplots(figsize=(14, h))
        sns.heatmap(pivot, cmap="RdYlBu_r", ax=ax, linewidths=0,
                    cbar_kws={"label": "Temperature (\u00b0F)"})
        ax.set_title("7-Day Temperature Forecast \u2014 All Bases",
                     fontsize=14, fontweight="bold")
        ax.set_ylabel("")
        ax.tick_params(axis="y", labelsize=max(3, min(6, 800 // len(pivot))))
        plt.tight_layout()
        plt.savefig(os.path.join(plot_dir, "7day_all_bases_temperature_heatmap.png"),
                    dpi=150, bbox_inches="tight")
        plt.close()

    if "cluster_id" in forecast_df.columns:
        summary_vars = [v for v in weather_vars if any(
            k in v for k in ["temperature_2m_mean", "precipitation_sum",
                              "wind_speed_10m_max", "cloud_cover_mean"]
        )][:4]
        if summary_vars:
            fig, axes = plt.subplots(1, len(summary_vars),
                                     figsize=(5 * len(summary_vars), 5))
            if len(summary_vars) == 1:
                axes = [axes]
            for i, var in enumerate(summary_vars):
                cluster_avgs = forecast_df.groupby("cluster_id")[var].mean()
                colors = ["#DC2626", "#2563EB", "#7C3AED"]
                labels_list = [CLUSTER_NAMES.get(int(c), f"C{int(c)}")
                               for c in cluster_avgs.index]
                bars = axes[i].bar(labels_list, cluster_avgs.values,
                                   color=colors[:len(labels_list)])
                axes[i].set_title(_nice_col(var), fontsize=10, fontweight="bold")
                axes[i].grid(True, alpha=0.3, axis="y")
                for bar, val in zip(bars, cluster_avgs.values):
                    axes[i].text(bar.get_x() + bar.get_width() / 2, bar.get_height(),
                                 f"{val:.1f}", ha="center", va="bottom", fontsize=8)
            plt.suptitle("7-Day Forecast Average by Cluster",
                         fontsize=13, fontweight="bold")
            plt.tight_layout()
            plt.savefig(os.path.join(plot_dir, "7day_cluster_forecast_summary.png"),
                        dpi=150, bbox_inches="tight")
            plt.close()

    if reg_model and hasattr(reg_model, "estimators_"):
        reg_target_cols = bundle["reg_target_cols"]
        orig_var_map = bundle["orig_var_map"]
        fi = []
        shown = 0
        for j, est in enumerate(reg_model.estimators_):
            if shown >= 10:
                break
            col = reg_target_cols[j]
            orig_var, transform = orig_var_map[col]
            if transform in ("wind_sin", "wind_cos"):
                continue
            b = est.get_booster()
            fnames = b.feature_names if b.feature_names else feature_cols
            for fn, fv in zip(fnames, est.feature_importances_):
                fi.append({"variable": _nice_col(orig_var), "feature": fn, "importance": fv})
            shown += 1

        if fi:
            fidf = pd.DataFrame(fi)
            piv = fidf.pivot_table(
                index="feature", columns="variable",
                values="importance", fill_value=0,
            )
            piv["_m"] = piv.mean(axis=1)
            piv = piv.nlargest(min(20, len(piv)), "_m").drop(columns="_m")

            fig, ax = plt.subplots(figsize=(max(10, len(piv.columns) * 1.2), 10))
            sns.heatmap(piv, cmap="YlOrRd", linewidths=0.4, annot=True, fmt=".3f", ax=ax)
            ax.set_title("Model Feature Importance (Top 20 Features \u00d7 Top 10 Variables)",
                         fontsize=13, fontweight="bold")
            plt.tight_layout()
            plt.savefig(os.path.join(plot_dir, "model_feature_importance.png"),
                        dpi=150, bbox_inches="tight")
            plt.close()

    print(f"\n  All charts saved -> {plot_dir}/")


def main():
    for d in ("data", "png"):
        os.makedirs(d, exist_ok=True)

    print("=" * 65)
    print("  7-DAY WEATHER PREDICTION MODEL")
    print("  (Unified Multi-Output XGBoost + Weather Code Classifier)")
    print("=" * 65)

    df = load_data()
    weather_vars = detect_weather_variables(df)
    if not weather_vars:
        raise ValueError("No weather variables found in historical data.")

    counts = df.groupby("base_name").size()
    usable = (counts >= CONFIG["min_days_required"]).sum()
    print(f"  Bases with >= {CONFIG['min_days_required']} days: {usable} / {len(counts)}")

    bundle, metrics = train_unified_model(df, weather_vars)

    forecast_df = predict_7days(df, bundle, weather_vars)

    save_outputs(forecast_df, bundle, metrics, df, weather_vars)

    if not forecast_df.empty:
        print(f"\n  Forecast: {forecast_df['date'].min()} -> {forecast_df['date'].max()}"
              f" | {forecast_df['base_name'].nunique()} bases")

    print("\n" + "=" * 65)
    print("  7-DAY PREDICTION COMPLETE")
    print("=" * 65)


if __name__ == "__main__":
    main()
