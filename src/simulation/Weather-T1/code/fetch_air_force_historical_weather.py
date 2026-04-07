from __future__ import annotations

import datetime as dt
import os
import time
from typing import Any
import re

import pandas as pd
import requests
from tqdm import tqdm


GEOCODED_FILE = "air_force_bases_geocoded_v2.csv"
INSTALLATIONS_XLSX = "midas_config_values.xlsx"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"

YEARS_BACK = 3
END_DATE = dt.date.today() - dt.timedelta(days=1)
START_DATE = END_DATE - dt.timedelta(days=365 * YEARS_BACK)

DAILY_VARS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "temperature_2m_mean",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "apparent_temperature_mean",
    "sunrise",
    "sunset",
    "daylight_duration",
    "sunshine_duration",
    "precipitation_sum",
    "rain_sum",
    "snowfall_sum",
    "precipitation_hours",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
    "wind_direction_10m_dominant",
    "shortwave_radiation_sum",
    "et0_fao_evapotranspiration",
    "relative_humidity_2m_max",
    "relative_humidity_2m_min",
    "surface_pressure_max",
    "surface_pressure_min",
    "cloud_cover_mean",
    "wind_speed_10m_mean",
    "wind_gusts_10m_mean",
]

def _output_name(start_date: dt.date, end_date: dt.date) -> str:
    return os.path.join("data", f"air_force_bases_historical_daily_era5_{start_date}_to_{end_date}.csv")


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


def load_air_force_bases() -> pd.DataFrame:
    df = pd.read_excel(INSTALLATIONS_XLSX, sheet_name="Installation Locations")
    required = {"Title", "Coordinates"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns in {INSTALLATIONS_XLSX}: {sorted(missing)}")

    rows = []
    for idx, row in df.iterrows():
        lat, lon = parse_dms_coordinates(str(row["Coordinates"]))
        if lat is None or lon is None:
            continue
        rows.append({
            "OBJECTID": idx + 1,
            "Site_Name": str(row["Title"]).strip(),
            "State": "",
            "Reporting_Component": "xlsx",
            "latitude": lat,
            "longitude": lon,
        })
    out = pd.DataFrame(rows)
    out = out.dropna(subset=["latitude", "longitude"]).reset_index(drop=True)
    return out


def fetch_batch(batch: pd.DataFrame, start_date: dt.date, end_date: dt.date, max_retries: int = 4) -> list[dict[str, Any]]:
    params = {
        "latitude": ",".join(f"{x:.6f}" for x in batch["latitude"].tolist()),
        "longitude": ",".join(f"{x:.6f}" for x in batch["longitude"].tolist()),
        "start_date": str(start_date),
        "end_date": str(end_date),
        "daily": ",".join(DAILY_VARS),
        "timezone": "auto",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "kmh",
        "precipitation_unit": "mm",
    }

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(ARCHIVE_URL, params=params, timeout=90)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else [data]
            if resp.status_code == 429:
                wait = 10 * attempt
                print(f"  Rate-limited (429), waiting {wait}s...")
                time.sleep(wait)
                continue
            print(f"  Archive API error {resp.status_code}: {resp.text[:250]}")
            return []
        except Exception as exc:
            if attempt == max_retries:
                print(f"  Request failed after retries: {exc}")
                return []
            time.sleep(5 * attempt)
    return []


def flatten_daily_row(base_info: dict[str, Any], payload: dict[str, Any]) -> list[dict[str, Any]]:
    daily = payload.get("daily", {})
    times = daily.get("time", [])
    rows: list[dict[str, Any]] = []

    for i, day in enumerate(times):
        row = dict(base_info)
        row["date"] = day
        for var in DAILY_VARS:
            vals = daily.get(var, [])
            row[f"daily_{var}"] = vals[i] if i < len(vals) else None
        rows.append(row)
    return rows


def iter_date_chunks(start_date: dt.date, end_date: dt.date, chunk_days: int = 365) -> list[tuple[dt.date, dt.date]]:
    chunks: list[tuple[dt.date, dt.date]] = []
    cursor = start_date
    while cursor <= end_date:
        chunk_end = min(cursor + dt.timedelta(days=chunk_days - 1), end_date)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + dt.timedelta(days=1)
    return chunks


def main() -> None:
    os.makedirs("data", exist_ok=True)
    print("=" * 72)
    print("AIR FORCE HISTORICAL WEATHER FETCH (Open-Meteo Archive)")
    print("=" * 72)
    print(f"Date window: {START_DATE} -> {END_DATE} ({YEARS_BACK} years target)")

    bases = load_air_force_bases()
    print(f"Air Force-related bases with coordinates: {len(bases)}")

    batch_size = 18
    date_chunks = iter_date_chunks(START_DATE, END_DATE, chunk_days=365)
    print(f"Date chunks: {len(date_chunks)} yearly window(s)")
    output_file = _output_name(START_DATE, END_DATE)
    existing_keys: set[tuple[Any, str]] = set()

    if os.path.exists(output_file):
        try:
            prior = pd.read_csv(output_file, usecols=["OBJECTID", "date"])
            existing_keys = set(zip(prior["OBJECTID"], prior["date"]))
            print(f"Resuming from existing file: {output_file} ({len(existing_keys):,} base-date rows)")
        except Exception:
            print("Could not read existing output for resume; starting fresh append mode.")

    all_rows: list[dict[str, Any]] = []

    for chunk_start, chunk_end in date_chunks:
        print(f"\nFetching chunk: {chunk_start} -> {chunk_end}")
        chunk_rows: list[dict[str, Any]] = []
        for start in tqdm(range(0, len(bases), batch_size), desc=f"Batches {chunk_start.year}"):
            batch = bases.iloc[start:start + batch_size].copy()
            results = fetch_batch(batch, chunk_start, chunk_end)
            if not results:
                continue

            for i, (_, base) in enumerate(batch.iterrows()):
                base_info = {
                    "OBJECTID": base["OBJECTID"],
                    "Site_Name": base["Site_Name"],
                    "State": base["State"],
                    "Reporting_Component": base["Reporting_Component"],
                    "latitude": base["latitude"],
                    "longitude": base["longitude"],
                }
                if i < len(results):
                    daily_rows = flatten_daily_row(base_info, results[i])
                    for r in daily_rows:
                        key = (r["OBJECTID"], r["date"])
                        if key not in existing_keys:
                            existing_keys.add(key)
                            chunk_rows.append(r)

            time.sleep(0.25)

        if chunk_rows:
            chunk_df = pd.DataFrame(chunk_rows)
            write_header = not os.path.exists(output_file)
            chunk_df.to_csv(output_file, mode="a", header=write_header, index=False)
            all_rows.extend(chunk_rows)
            print(f"  Appended {len(chunk_rows):,} rows for chunk {chunk_start.year}.")

    if not os.path.exists(output_file):
        raise RuntimeError("No historical rows were fetched.")

    out = pd.read_csv(output_file)

    out["date"] = pd.to_datetime(out["date"])
    coverage = out.groupby("Site_Name")["date"].agg(["min", "max", "count"])
    coverage["years"] = (coverage["max"] - coverage["min"]).dt.days / 365.25

    print(f"\n  Saved: {output_file}")
    print(f"  {len(out):,} rows | {out['Site_Name'].nunique()} bases | "
          f"{out['date'].min().date()} -> {out['date'].max().date()}")






    print("=" * 72)


if __name__ == "__main__":
    main()
