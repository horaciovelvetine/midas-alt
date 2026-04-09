"""Config sheet and distribution parsing for the MIDAS configuration workbook."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import pandas as pd
from pandas import ExcelFile

from src.config.settings import (
    DegradationSettings,
    OutputSettings,
    SimulationDistributions,
    SimulationSettings,
)
from src.functions import create_distribution_from_spec
from src.models.distributions import (
    DistributionBase,
    WeightedProbabilityDistribution,
    WeightedProbabilitySegment,
)

logger = logging.getLogger(__name__)

PARAMETER_KEY_MAP: dict[str, str] = {
    "condition index degraded threshold": "condition_index_degraded_threshold",
    "resiliency grade threshold": "resiliency_grade_threshold",
    "initial condition index": "initial_condition_index",
    "maximum time series years history": "max_time_series_years",
    "facilities per installation": "facilities_per_installation",
    "dependency chain group range": "dependency_chain_group_range",
    "maximum vertical depth": "max_vertical_depth",
    "max vertical depth": "max_vertical_depth",
    "dependency chain vertical depth": "max_vertical_depth",
    "maximum dependency chain vertical depth": "max_vertical_depth",
    "maximum system age": "maximum_system_age",
    "maximum facility age": "maximum_facility_age",
    "facility condition randomly degrades chance": "facility_condition_randomly_degrades_chance",
    "output excel sheet main name": "excel_sheet_main",
    "output excel sheet facility ts name": "excel_sheet_facility_ts",
    "output excel sheet system ts name": "excel_sheet_system_ts",
    "output excel sheet work orders name": "excel_sheet_work_orders",
    "output excel sheet metadata name": "excel_sheet_metadata",
    "outputed metadata file suffix": "metadata_file_suffix",
    "outputs csv table separator": "csv_table_separator",
    "simulated condition index distribution": "condition_index_distribution",
    "simulated age distribution": "age_distribution",
    "simulated grade distribution": "grade_distribution",
    "simulated work order count distribution": "work_order_count_distribution",
    "simulated work order status distribution": "work_order_status_distribution",
    "simulated work order priority distribution": "work_order_priority_distribution",
    "simulated work order requesting organization distribution": "work_order_requesting_organization_distribution",
}


def _normalize_parameter_key(param: str) -> str:
    """Normalize a config parameter name to its internal key."""
    normalized = str(param).strip().lower()
    if normalized in PARAMETER_KEY_MAP:
        return PARAMETER_KEY_MAP[normalized]
    return normalized.replace(" ", "_")


def _parse_range(value: str | int | float) -> tuple[int, int]:
    """Parse a range value like `8-14` or a single value like `10`."""
    if isinstance(value, (int, float)):
        parsed = int(value)
        return (parsed, parsed)

    value_str = str(value).strip()
    if "-" in value_str:
        parts = value_str.split("-")
        if len(parts) == 2:
            try:
                return (int(parts[0].strip()), int(parts[1].strip()))
            except ValueError:
                pass

    try:
        parsed = int(value_str)
        return (parsed, parsed)
    except ValueError:
        return (8, 14)


def _load_config_values(
    excel_file: ExcelFile,
) -> tuple[DegradationSettings, SimulationSettings, OutputSettings, dict[str, Any]]:
    """Load scalar configuration values from the `Config` sheet."""
    if "Config" not in excel_file.sheet_names:
        return DegradationSettings(), SimulationSettings(), OutputSettings(), {}

    df = pd.read_excel(excel_file, sheet_name="Config")
    config_dict: dict[str, Any] = {}

    for _, row in df.iterrows():
        param = row.get("Parameter") or row.get("Key") or row.get("Setting")
        value = row.get("Value")
        if pd.isna(value):
            value = row.get("Default")

        if not pd.isna(param) and not pd.isna(value):
            config_dict[_normalize_parameter_key(param)] = value

    degradation = DegradationSettings(
        condition_index_degraded_threshold=float(
            config_dict.get("condition_index_degraded_threshold", 25.0)
        ),
        resiliency_grade_threshold=int(
            config_dict.get("resiliency_grade_threshold", 70)
        ),
        initial_condition_index=float(
            config_dict.get("initial_condition_index", 99.99)
        ),
        max_time_series_years=int(config_dict.get("max_time_series_years", 10)),
    )

    facilities_range = _parse_range(
        config_dict.get("facilities_per_installation", "8-14")
    )
    dep_chain_range = _parse_range(
        config_dict.get("dependency_chain_group_range", "1-3")
    )

    simulation = SimulationSettings(
        facilities_per_installation=facilities_range,
        dependency_chain_group_range=dep_chain_range,
        max_vertical_depth=int(config_dict.get("max_vertical_depth", 3)),
        maximum_system_age=int(config_dict.get("maximum_system_age", 80)),
        maximum_facility_age=int(config_dict.get("maximum_facility_age", 80)),
        facility_condition_randomly_degrades_chance=int(
            config_dict.get("facility_condition_randomly_degrades_chance", 35)
        ),
    )

    output = OutputSettings(
        excel_sheet_main=str(config_dict.get("excel_sheet_main", "Main Data")).strip(),
        excel_sheet_facility_ts=str(
            config_dict.get("excel_sheet_facility_ts", "Facility Time Series")
        ).strip(),
        excel_sheet_system_ts=str(
            config_dict.get("excel_sheet_system_ts", "System Time Series")
        ).strip(),
        excel_sheet_work_orders=str(
            config_dict.get("excel_sheet_work_orders", "Work Orders")
        ).strip(),
        excel_sheet_metadata=str(
            config_dict.get("excel_sheet_metadata", "_metadata")
        ).strip(),
        metadata_file_suffix=str(
            config_dict.get("metadata_file_suffix", "_metadata.json")
        ).strip(),
        csv_table_separator=str(config_dict.get("csv_table_separator", "_")).strip(),
    )

    return degradation, simulation, output, config_dict


def _parse_distribution_string(value: str) -> list[tuple[int, str]] | None:
    """Parse `percentage/value` style distribution text from workbook cells."""
    if not value or pd.isna(value):
        return None

    value_str = str(value).strip()
    segments: list[tuple[int, str]] = []
    lines = re.split(r"\n|(?=\d+:\s*\()", value_str)

    for line in lines:
        item = line.strip()
        if not item:
            continue

        match = re.match(r"(?:\d+:\s*)?\(?\s*(\d+)\s*[,:]\s*([\d\-]+)\s*\)?", item)
        if match:
            segments.append((int(match.group(1)), match.group(2).strip()))
            continue

        match = re.match(r"G(\d+)\s*:\s*(\d+)", item)
        if match:
            segments.append((int(match.group(2)), match.group(1)))

    return segments if segments else None


def _parse_weighted_category_distribution(value: str) -> list[tuple[int, str]] | None:
    """Parse weighted categorical lines into `(percentage, value)` tuples."""
    if not value or pd.isna(value):
        return None

    value_str = str(value).strip()
    if not value_str:
        return None
    value_str = value_str.replace("\\n", "\n")

    segments: list[tuple[int, str]] = []
    for line in value_str.splitlines():
        item = line.strip()
        if not item:
            continue

        match = re.match(r"(.+?)\s*:\s*(\d+)\s*$", item)
        if match:
            segments.append((int(match.group(2)), match.group(1).strip()))
            continue

        match = re.match(r"(\d+)\s*:\s*(.+?)\s*$", item)
        if match:
            segments.append((int(match.group(1)), match.group(2).strip()))

    return segments if segments else None


def _parse_distribution_spec(value: Any) -> dict[str, Any] | None:
    """Parse a JSON distribution spec from a workbook cell."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if not text or not text.startswith("{"):
        return None
    try:
        spec = json.loads(text)
    except json.JSONDecodeError:
        return None
    return spec if isinstance(spec, dict) else None


def _load_distributions(config_dict: dict[str, Any]) -> SimulationDistributions:
    """Load configured distribution objects from a normalized config dict."""
    condition_index: WeightedProbabilityDistribution | None = None
    age: WeightedProbabilityDistribution | None = None
    grade: WeightedProbabilityDistribution | None = None
    work_order_count: DistributionBase | None = None
    work_order_status: WeightedProbabilityDistribution | None = None
    work_order_priority: WeightedProbabilityDistribution | None = None
    work_order_requesting_organization: WeightedProbabilityDistribution | None = None

    ci_str = config_dict.get("condition_index_distribution")
    if ci_str:
        segments = _parse_distribution_string(ci_str)
        if segments:
            try:
                condition_index = WeightedProbabilityDistribution(
                    [WeightedProbabilitySegment(pct, val) for pct, val in segments]
                )
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to parse condition index distribution: %s", exc)

    age_str = config_dict.get("age_distribution")
    if age_str:
        segments = _parse_distribution_string(age_str)
        if segments:
            try:
                age = WeightedProbabilityDistribution(
                    [WeightedProbabilitySegment(pct, val) for pct, val in segments]
                )
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to parse age distribution: %s", exc)

    grade_str = config_dict.get("grade_distribution")
    if grade_str:
        segments = _parse_distribution_string(grade_str)
        if segments:
            try:
                grade = WeightedProbabilityDistribution(
                    [WeightedProbabilitySegment(pct, val) for pct, val in segments]
                )
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to parse grade distribution: %s", exc)

    wo_count_config = config_dict.get("work_order_count_distribution")
    if wo_count_config:
        spec = _parse_distribution_spec(wo_count_config)
        if spec:
            try:
                work_order_count = create_distribution_from_spec(spec)
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to parse work-order count spec: %s", exc)
        else:
            segments = _parse_distribution_string(str(wo_count_config))
            if segments:
                try:
                    work_order_count = WeightedProbabilityDistribution(
                        [WeightedProbabilitySegment(pct, val) for pct, val in segments]
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Failed to parse work-order count distribution: %s", exc
                    )

    wo_status_config = config_dict.get("work_order_status_distribution")
    if wo_status_config:
        spec = _parse_distribution_spec(wo_status_config)
        if spec:
            try:
                maybe_dist = create_distribution_from_spec(spec)
                if isinstance(maybe_dist, WeightedProbabilityDistribution):
                    work_order_status = maybe_dist
                else:
                    logger.warning(
                        "work_order_status_distribution must resolve to weighted segments"
                    )
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to parse work-order status spec: %s", exc)
        else:
            segments = _parse_weighted_category_distribution(str(wo_status_config))
            if segments:
                try:
                    work_order_status = WeightedProbabilityDistribution(
                        [WeightedProbabilitySegment(pct, val) for pct, val in segments]
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Failed to parse work-order status distribution: %s", exc
                    )

    wo_priority_config = config_dict.get("work_order_priority_distribution")
    if wo_priority_config:
        spec = _parse_distribution_spec(wo_priority_config)
        if spec:
            try:
                maybe_dist = create_distribution_from_spec(spec)
                if isinstance(maybe_dist, WeightedProbabilityDistribution):
                    work_order_priority = maybe_dist
                else:
                    logger.warning(
                        "work_order_priority_distribution must resolve to weighted segments"
                    )
            except (TypeError, ValueError) as exc:
                logger.warning("Failed to parse work-order priority spec: %s", exc)
        else:
            segments = _parse_weighted_category_distribution(str(wo_priority_config))
            if segments:
                try:
                    work_order_priority = WeightedProbabilityDistribution(
                        [WeightedProbabilitySegment(pct, val) for pct, val in segments]
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Failed to parse work-order priority distribution: %s", exc
                    )

    wo_requesting_org_config = config_dict.get(
        "work_order_requesting_organization_distribution"
    )
    if wo_requesting_org_config:
        spec = _parse_distribution_spec(wo_requesting_org_config)
        if spec:
            try:
                maybe_dist = create_distribution_from_spec(spec)
                if isinstance(maybe_dist, WeightedProbabilityDistribution):
                    work_order_requesting_organization = maybe_dist
                else:
                    logger.warning(
                        "work_order_requesting_organization_distribution must resolve to weighted segments"
                    )
            except (TypeError, ValueError) as exc:
                logger.warning(
                    "Failed to parse work-order requesting organization spec: %s", exc
                )
        else:
            segments = _parse_weighted_category_distribution(
                str(wo_requesting_org_config)
            )
            if segments:
                try:
                    work_order_requesting_organization = (
                        WeightedProbabilityDistribution(
                            [
                                WeightedProbabilitySegment(pct, val)
                                for pct, val in segments
                            ]
                        )
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning(
                        "Failed to parse work-order requesting organization distribution: %s",
                        exc,
                    )

    return SimulationDistributions(
        condition_index=condition_index,
        age=age,
        grade=grade,
        work_order_count=work_order_count,
        work_order_status=work_order_status,
        work_order_priority=work_order_priority,
        work_order_requesting_organization=work_order_requesting_organization,
    )
