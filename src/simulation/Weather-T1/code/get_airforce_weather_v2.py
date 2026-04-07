import pandas as pd
import numpy as np
import requests
import time
import json
import os
import re
from tqdm import tqdm

CSV_PATH = "NTAD_Military_Bases_-1644289556481787667.csv"
INSTALLATIONS_XLSX = "midas_config_values.xlsx"
ARCGIS_URL = "https://services.arcgis.com/xOi1kZaI0eWDREZv/arcgis/rest/services/NTAD_Military_Bases/FeatureServer/0/query"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"

OUTPUT_GEOCODED = os.path.join("data", "base_locations.csv")
OUTPUT_WEATHER  = os.path.join("data", "current_weather_snapshot.csv")
OUTPUT_DAILY    = os.path.join("data", "7day_forecast_raw.csv")

CURRENT_VARS = [
    "temperature_2m", "relative_humidity_2m", "apparent_temperature",
    "is_day", "precipitation", "rain", "showers", "snowfall",
    "weather_code", "cloud_cover", "pressure_msl", "surface_pressure",
    "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
]

DAILY_VARS = [
    "weather_code",
    "temperature_2m_max", "temperature_2m_min", "temperature_2m_mean",
    "apparent_temperature_max", "apparent_temperature_min", "apparent_temperature_mean",
    "sunrise", "sunset",
    "daylight_duration", "sunshine_duration",
    "uv_index_max", "uv_index_clear_sky_max",
    "precipitation_sum", "rain_sum", "showers_sum", "snowfall_sum",
    "precipitation_hours",
    "precipitation_probability_max",
    "precipitation_probability_mean", "precipitation_probability_min",
    "wind_speed_10m_max", "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
]

HOURLY_VARS = [
    "temperature_2m", "relative_humidity_2m", "dew_point_2m",
    "apparent_temperature", "precipitation_probability",
    "precipitation", "rain", "showers", "snowfall", "snow_depth",
    "weather_code", "pressure_msl", "surface_pressure",
    "cloud_cover", "cloud_cover_low", "cloud_cover_mid", "cloud_cover_high",
    "visibility", "evapotranspiration", "et0_fao_evapotranspiration",
    "vapour_pressure_deficit",
    "wind_speed_10m", "wind_speed_80m",
    "wind_direction_10m", "wind_direction_80m",
    "wind_gusts_10m",
    "temperature_80m",
    "soil_temperature_0cm", "soil_temperature_6cm",
    "soil_moisture_0_to_1cm", "soil_moisture_1_to_3cm",
    "uv_index", "uv_index_clear_sky", "is_day", "sunshine_duration",
    "wet_bulb_temperature_2m", "cape",
    "freezing_level_height", "boundary_layer_height",
    "shortwave_radiation", "direct_radiation", "diffuse_radiation",
    "direct_normal_irradiance",
]


def parse_dms_coordinates(coord_text: str):
    if not isinstance(coord_text, str):
        return None, None
    text = coord_text.upper()
    nums = re.findall(r"\d+", text)
    dirs = re.findall(r"[NSEW]", text)
    if len(nums) < 4 or len(dirs) < 2:
        return None, None

    try:
        lat_deg = float(nums[0])
        lat_min = float(nums[1]) if len(nums) >= 2 else 0.0
        lat_sec = float(nums[2]) if len(nums) >= 3 and len(nums) >= 6 else 0.0

        lon_start = 3 if len(nums) >= 6 else 2
        lon_deg = float(nums[lon_start])
        lon_min = float(nums[lon_start + 1]) if len(nums) > lon_start + 1 else 0.0
        lon_sec = float(nums[lon_start + 2]) if len(nums) > lon_start + 2 else 0.0

        lat = lat_deg + (lat_min / 60.0) + (lat_sec / 3600.0)
        lon = lon_deg + (lon_min / 60.0) + (lon_sec / 3600.0)
        if dirs[0] == "S":
            lat *= -1.0
        if dirs[1] == "W":
            lon *= -1.0
        return lat, lon
    except Exception:
        return None, None


def load_bases_from_midas_xlsx() -> pd.DataFrame:
    print(f"Loading installation coordinates from {INSTALLATIONS_XLSX}...")
    df = pd.read_excel(INSTALLATIONS_XLSX, sheet_name="Installation Locations")
    needed = {"Title", "Location", "Region", "Coordinates"}
    missing = needed - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {INSTALLATIONS_XLSX}: {sorted(missing)}")

    rows = []
    for idx, row in df.iterrows():
        lat, lon = parse_dms_coordinates(str(row["Coordinates"]))
        rows.append({
            "OBJECTID": idx + 1,
            "Site_Name": str(row["Title"]).strip(),
            "State": "",
            "Operational_Status": "act",
            "Reporting_Component": "xlsx",
            "Is_Joint_Base": "",
            "latitude": lat,
            "longitude": lon,
            "Location": str(row.get("Location", "")),
            "Region": str(row.get("Region", "")),
            "Coordinates": str(row.get("Coordinates", "")),
        })

    out = pd.DataFrame(rows)
    valid = out["latitude"].notna().sum()
    print(f"  Parsed coordinates: {valid}/{len(out)} installations")
    out.to_csv(OUTPUT_GEOCODED, index=False)
    print(f"  Saved: {OUTPUT_GEOCODED}")
    return out


def compute_polygon_centroid(rings: list) -> tuple:
    all_lons = []
    all_lats = []
    for ring in rings:
        for point in ring:
            all_lons.append(point[0])
            all_lats.append(point[1])

    if not all_lons:
        return None, None

    return np.mean(all_lats), np.mean(all_lons)


def fetch_all_base_coordinates() -> pd.DataFrame:
    print("Fetching base geometries from BTS ArcGIS API...")

    resp0 = requests.get(ARCGIS_URL, params={
        "where": "1=1", "outFields": "OBJECTID", "returnGeometry": "false",
        "f": "json", "resultRecordCount": "2000"
    }, timeout=30)
    all_ids = [f["attributes"]["OBJECTID"] for f in resp0.json().get("features", [])]
    print(f"  Found {len(all_ids)} base IDs")

    all_features = []
    batch_size = 50

    for i in tqdm(range(0, len(all_ids), batch_size), desc="Fetching geometry"):
        batch_ids = all_ids[i:i + batch_size]
        id_list = ",".join(str(x) for x in batch_ids)
        where_clause = f"OBJECTID IN ({id_list})"

        params = {
            "where": where_clause,
            "outFields": "OBJECTID,siteName,stateNameCode,siteOperationalStatus,siteReportingComponent,isJointBase",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "json",
            "resultRecordCount": "100",
            "maxAllowableOffset": "0.01",
        }

        try:
            resp = requests.get(ARCGIS_URL, params=params, timeout=60)
            if resp.status_code != 200:
                print(f"  API error {resp.status_code} for batch starting at {i}")
                continue

            data = resp.json()
            features = data.get("features", [])
            all_features.extend(features)
        except Exception as e:
            print(f"  Error fetching batch at {i}: {e}")

        time.sleep(0.15)

    rows = []
    for feat in all_features:
        attrs = feat.get("attributes", {})
        geom = feat.get("geometry", {})
        rings = geom.get("rings", [])

        lat, lon = compute_polygon_centroid(rings)

        rows.append({
            "OBJECTID": attrs.get("OBJECTID"),
            "Site_Name": attrs.get("siteName", ""),
            "State": attrs.get("stateNameCode", ""),
            "Operational_Status": attrs.get("siteOperationalStatus", ""),
            "Reporting_Component": attrs.get("siteReportingComponent", ""),
            "Is_Joint_Base": attrs.get("isJointBase", ""),
            "latitude": lat,
            "longitude": lon,
        })

    df = pd.DataFrame(rows)

    valid = df["latitude"].notna().sum()
    print(f"  Successfully computed centroids: {valid}/{len(df)}")

    df.to_csv(OUTPUT_GEOCODED, index=False)
    print(f"  Saved: {OUTPUT_GEOCODED}")

    return df


def fetch_weather_batch(latitudes: list, longitudes: list,
                        include_daily=True, max_retries=5) -> list:
    params = {
        "latitude": ",".join(f"{x:.6f}" for x in latitudes),
        "longitude": ",".join(f"{x:.6f}" for x in longitudes),
        "current": ",".join(CURRENT_VARS),
        "timezone": "auto",
        "forecast_days": 7,
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
        "timeformat": "iso8601",
    }

    if include_daily:
        params["daily"] = ",".join(DAILY_VARS)

    for attempt in range(max_retries):
        try:
            resp = requests.get(FORECAST_URL, params=params, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list):
                    return data
                else:
                    return [data]
            elif resp.status_code == 429:
                wait = 65 + attempt * 10
                print(f"    Rate limited (429). Waiting {wait}s before retry {attempt+1}/{max_retries}...")
                time.sleep(wait)
                continue
            else:
                print(f"    API error {resp.status_code}: {resp.text[:200]}")
                return []
        except Exception as e:
            print(f"    Request error: {e}")
            if attempt < max_retries - 1:
                time.sleep(10)
                continue
            return []

    print("    Max retries reached, skipping batch")
    return []


def fetch_all_weather(df: pd.DataFrame) -> tuple:
    valid = df.dropna(subset=["latitude", "longitude"]).copy()

    if "Reporting_Component" in valid.columns:
        airforce_components = {"usaf", "airNationalGuard", "afr"}
        before = len(valid)
        if valid["Reporting_Component"].isin(airforce_components).any():
            valid = valid[valid["Reporting_Component"].isin(airforce_components)].copy()
            print(f"\nFetching weather for {len(valid)} Air Force-related bases "
                  f"out of {before} total with coordinates...")
        else:
            print(f"\nFetching weather for {len(valid)} installations from MIDAS list...")
    else:
        print(f"\nFetching weather for {len(valid)} bases (no Reporting_Component column found)...")

    partial_current = []
    partial_daily = []
    done_ids = set()
    valid_site_names = set(valid["Site_Name"].astype(str).tolist())
    if os.path.exists(OUTPUT_WEATHER):
        try:
            prev = pd.read_csv(OUTPUT_WEATHER)
            if "current_temperature_2m" in prev.columns and "Site_Name" in prev.columns:
                has_data = prev["current_temperature_2m"].notna()
                prev = prev[has_data].copy()
                prev = prev[prev["Site_Name"].astype(str).isin(valid_site_names)]
                prev = prev.drop_duplicates(subset=["Site_Name"], keep="last")
                partial_current = prev.to_dict("records")
                done_ids = set(prev["OBJECTID"].tolist())
                print(f"  Resuming: {len(done_ids)} bases already have weather data")
        except Exception:
            pass

    if os.path.exists(OUTPUT_DAILY) and done_ids:
        try:
            prev_d = pd.read_csv(OUTPUT_DAILY)
            if "Site_Name" in prev_d.columns and "date" in prev_d.columns:
                prev_d = prev_d[prev_d["Site_Name"].astype(str).isin(valid_site_names)].copy()
                prev_d = prev_d.drop_duplicates(subset=["Site_Name", "date"], keep="last")
                partial_daily = prev_d.to_dict("records")
        except Exception:
            pass

    remaining = valid[~valid["OBJECTID"].isin(done_ids)]
    print(f"  Remaining bases to fetch: {len(remaining)}")

    BATCH_SIZE = 20
    current_rows = list(partial_current)
    daily_rows = list(partial_daily)

    for start in tqdm(range(0, len(remaining), BATCH_SIZE), desc="Weather batches"):
        batch = remaining.iloc[start: start + BATCH_SIZE]
        lats = batch["latitude"].tolist()
        lons = batch["longitude"].tolist()

        results = fetch_weather_batch(lats, lons, include_daily=True)

        if not results:
            print("    Batch failed \u2014 trying individual requests...")
            for idx in range(len(batch)):
                single = fetch_weather_batch([lats[idx]], [lons[idx]], include_daily=True)
                if single:
                    results.append(single[0])
                else:
                    results.append({})
                time.sleep(1)

        for i, (_, row) in enumerate(batch.iterrows()):
            base_info = {
                "OBJECTID": row["OBJECTID"],
                "Site_Name": row["Site_Name"],
                "State": row["State"],
                "latitude": row["latitude"],
                "longitude": row["longitude"],
                "Operational_Status": row.get("Operational_Status", ""),
                "Reporting_Component": row.get("Reporting_Component", ""),
                "Is_Joint_Base": row.get("Is_Joint_Base", ""),
            }

            if i < len(results) and results[i]:
                weather = results[i]

                current = weather.get("current", {})
                current_row = {**base_info}
                current_row["timezone"] = weather.get("timezone", "")
                current_row["current_time"] = current.get("time", "")
                for var in CURRENT_VARS:
                    current_row[f"current_{var}"] = current.get(var)
                current_rows.append(current_row)

                daily = weather.get("daily", {})
                times = daily.get("time", [])
                for day_idx, day_date in enumerate(times):
                    day_row = {**base_info}
                    day_row["date"] = day_date
                    for var in DAILY_VARS:
                        vals = daily.get(var, [])
                        day_row[f"daily_{var}"] = vals[day_idx] if day_idx < len(vals) else None
                    daily_rows.append(day_row)
            else:
                current_rows.append(base_info)

        pd.DataFrame(current_rows).to_csv(OUTPUT_WEATHER, index=False)
        pd.DataFrame(daily_rows).to_csv(OUTPUT_DAILY, index=False)

        time.sleep(2)

    current_df = pd.DataFrame(current_rows)
    daily_df = pd.DataFrame(daily_rows)

    if "Site_Name" in current_df.columns:
        current_df = current_df.drop_duplicates(subset=["Site_Name"], keep="last")
    if "Site_Name" in daily_df.columns and "date" in daily_df.columns:
        daily_df = daily_df.drop_duplicates(subset=["Site_Name", "date"], keep="last")

    current_df.to_csv(OUTPUT_WEATHER, index=False)
    daily_df.to_csv(OUTPUT_DAILY, index=False)

    print(f"\nSaved: {OUTPUT_WEATHER}  ({len(current_df)} rows, {len(current_df.columns)} cols)")
    print(f"Saved: {OUTPUT_DAILY}  ({len(daily_df)} rows, {len(daily_df.columns)} cols)")

    return current_df, daily_df


def main():
    os.makedirs("data", exist_ok=True)
    print("=" * 65)
    print("  AIR FORCE BASES WEATHER FETCHER v2")
    print("=" * 65)

    if os.path.exists(OUTPUT_GEOCODED):
        print(f"\nFound cached {OUTPUT_GEOCODED}, loading...")
        df = pd.read_csv(OUTPUT_GEOCODED)
        valid = df["latitude"].notna().sum()
        print(f"  {valid}/{len(df)} installations with coordinates")
        if len(df) < 150 or valid < (len(df) * 0.9):
            print("  Cache appears incomplete \u2014 rebuilding from MIDAS XLSX...")
            df = load_bases_from_midas_xlsx()
    else:
        df = load_bases_from_midas_xlsx()

    current_df, daily_df = fetch_all_weather(df)

    print("\n" + "=" * 65)
    print("  SUMMARY")
    print("=" * 65)
    print(f"  Total installations in source : {len(df)}")
    print(f"  Bases with coordinates        : {df['latitude'].notna().sum()}")
    print(f"  Current weather rows          : {len(current_df)}")
    print(f"  Daily forecast rows           : {len(daily_df)}")
    print(f"  Current weather features      : {len(CURRENT_VARS)}")
    print(f"  Daily weather features        : {len(DAILY_VARS)}")
    print("=" * 65)


if __name__ == "__main__":
    main()
