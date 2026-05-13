"""Load exported simulation datasets back into domain objects."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from src.config.midas_config_data import MidasConfigData
from src.config.midas_settings import MidasSettings
from src.enums import UFCGrade, WO_Priority, WO_Status, WO_TradeSkill
from src.models import (
    DataStore,
    DependencyPosition,
    Facility,
    Installation,
    System,
    WorkOrder,
)

_REQUIRED_TABLES = ("installations", "facilities", "systems", "work_orders")


class SimulationDataLoader:
    """Rehydrate domain entities from normalized CSV or XLSX exports."""

    def __init__(self) -> None:
        """Initialize loader; settings/reference data come from singletons."""
        self.settings = MidasSettings()
        self.config_data = MidasConfigData()

    def load(self, dataset_path: str | Path) -> DataStore:
        """Load a normalized dataset directory or workbook."""
        path = Path(dataset_path).expanduser().resolve()
        if path.is_dir():
            tables = self._load_csv_tables(path)
        elif path.is_file() and path.suffix.lower() == ".xlsx":
            tables = self._load_excel_tables(path)
        else:
            raise ValueError("SimulationDataLoader expects a normalized CSV dataset directory or an XLSX workbook path")
        return self._build_data_store(tables)

    def _load_csv_tables(self, dataset_directory: Path) -> dict[str, pd.DataFrame]:
        """Load normalized CSV tables from an export directory."""
        tables: dict[str, pd.DataFrame] = {}
        separator = self.settings.get_value("csv_table_separator")

        for table_name in _REQUIRED_TABLES:
            candidates = sorted(dataset_directory.glob(f"*{separator}{table_name}.csv"))
            if not candidates:
                candidates = sorted(dataset_directory.glob(f"{table_name}.csv"))
            if not candidates:
                raise ValueError(f"Missing required CSV table '{table_name}' in {dataset_directory}")
            if len(candidates) > 1:
                raise ValueError(f"Multiple CSV files matched '{table_name}' in {dataset_directory}")
            tables[table_name] = pd.read_csv(candidates[0])

        return tables

    def _load_excel_tables(self, workbook_path: Path) -> dict[str, pd.DataFrame]:
        """Load normalized tables from an XLSX workbook."""
        workbook = pd.ExcelFile(workbook_path)
        sheet_names = set(workbook.sheet_names)
        required_sheets = {
            "installations": "Installations",
            "facilities": "Facilities",
            "systems": "Systems",
            "work_orders": self.settings.get_value("excel_sheet_work_orders"),
        }

        missing = [sheet_name for sheet_name in required_sheets.values() if sheet_name not in sheet_names]
        if missing:
            raise ValueError(f"Workbook is missing required sheets: {', '.join(missing)}")

        return {
            table_name: pd.read_excel(workbook_path, sheet_name=sheet_name) for table_name, sheet_name in required_sheets.items()
        }

    def _build_data_store(self, tables: dict[str, pd.DataFrame]) -> DataStore:
        """Convert exported tables into domain objects with restored relationships."""
        installations = self._build_installations(tables["installations"])
        facilities = self._build_facilities(tables["facilities"])
        systems = self._build_systems(tables["systems"])
        work_orders = self._build_work_orders(tables["work_orders"])

        installations_by_id = {installation.id: installation for installation in installations}
        facilities_by_id = {facility.id: facility for facility in facilities}
        systems_by_id = {system.id: system for system in systems}

        for facility in facilities:
            if facility.installation_id and facility.installation_id in installations_by_id:
                installations_by_id[facility.installation_id].facility_ids.append(facility.id)

        for system in systems:
            if system.facility_id and system.facility_id in facilities_by_id:
                facilities_by_id[system.facility_id].system_ids.append(system.id)

        for work_order in work_orders:
            if work_order.system_id and work_order.system_id in systems_by_id:
                systems_by_id[work_order.system_id].work_orders.append(work_order)

        return DataStore(
            installations=installations,
            facilities=facilities,
            systems=systems,
            work_orders=work_orders,
        )

    def _build_installations(self, table: pd.DataFrame) -> list[Installation]:
        """Build installation objects from an installations table."""
        installations: list[Installation] = []
        for row in table.to_dict(orient="records"):
            installations.append(
                Installation(
                    id=_required_text(row, "id"),
                    title=_text(row, "title"),
                    location=_text(row, "location"),
                    region=_text(row, "region"),
                    coordinates=_text(row, "coordinates"),
                    condition_index=_float_value(row, "condition_index"),
                )
            )
        return installations

    def _build_facilities(self, table: pd.DataFrame) -> list[Facility]:
        """Build facility objects from a facilities table."""
        facilities: list[Facility] = []
        for row in table.to_dict(orient="records"):
            dependency_value = _text(row, "dependency_chain")
            type_key = _int_value(row, "facility_type_key")
            title_from_export = _text(row, "title")
            resolved_title = title_from_export
            if not resolved_title and type_key is not None:
                ft = self.config_data.get_facility_type(type_key)
                resolved_title = ft.title if ft else None
            facilities.append(
                Facility(
                    id=_required_text(row, "id"),
                    facility_type_key=type_key,
                    facility_type_title=resolved_title,
                    year_constructed=_int_value(row, "year_constructed"),
                    dependency_position=DependencyPosition.from_string(dependency_value or "A1"),
                    resiliency_grade=UFCGrade.from_value(row.get("resiliency_grade")),
                    installation_id=_text(row, "installation_id"),
                    condition_index=_float_value(row, "condition_index"),
                )
            )
        return facilities

    def _build_systems(self, table: pd.DataFrame) -> list[System]:
        """Build system objects from a systems table."""
        systems: list[System] = []
        for row in table.to_dict(orient="records"):
            systems.append(
                System(
                    id=_required_text(row, "id"),
                    system_type_key=_int_value(row, "system_type_key"),
                    year_constructed=_int_value(row, "year_constructed"),
                    condition_index=_float_value(row, "condition_index"),
                    facility_id=_text(row, "facility_id"),
                )
            )
        return systems

    def _build_work_orders(self, table: pd.DataFrame) -> list[WorkOrder]:
        """Build work-order objects from a work-orders table."""
        work_orders: list[WorkOrder] = []
        for row in table.to_dict(orient="records"):
            work_orders.append(
                WorkOrder(
                    id=_required_text(row, "id"),
                    installation_id=_text(row, "installation_id"),
                    facility_id=_text(row, "facility_id"),
                    system_id=_text(row, "system_id"),
                    requesting_organization=_text(row, "requesting_organization"),
                    work_category=_text(row, "work_category"),
                    request_datetime=_datetime_value(row, "request_datetime"),
                    completion_datetime=_datetime_value(row, "completion_datetime"),
                    status=_enum_value(WO_Status, row.get("status")),
                    trade=_enum_value(WO_TradeSkill, row.get("trade")),
                    priority=_enum_value(WO_Priority, row.get("priority")),
                    problem_description=_text(row, "problem_description"),
                    requested_action=_text(row, "requested_action"),
                    actions_taken=_text(row, "actions_taken"),
                    impacts_mission=_bool_value(row.get("impacts_mission")),
                )
            )
        return work_orders


def _required_text(row: dict[str, Any], key: str) -> str:
    """Return a required text value or raise a clear error."""
    value = _text(row, key)
    if value is None:
        raise ValueError(f"Missing required value for '{key}'")
    return value


def _text(row: dict[str, Any], key: str) -> str | None:
    """Return a string value if present and non-empty."""
    value = row.get(key)
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def _int_value(row: dict[str, Any], key: str) -> int | None:
    """Return an integer value if present."""
    value = row.get(key)
    if pd.isna(value):
        return None
    return int(value)


def _float_value(row: dict[str, Any], key: str) -> float | None:
    """Return a float value if present."""
    value = row.get(key)
    if pd.isna(value):
        return None
    return float(value)


def _datetime_value(row: dict[str, Any], key: str):
    """Return a Python datetime value if present."""
    value = row.get(key)
    if pd.isna(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _bool_value(value: Any) -> bool:
    """Parse a bool-like value from CSV/XLSX data."""
    if pd.isna(value):
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in {"1", "true", "t", "yes", "y"}


def _enum_value(enum_cls, value: Any):
    """Parse an enum value by member name or exported string value."""
    if pd.isna(value):
        return None
    text = str(value).strip().lower()
    for enum_value in enum_cls:
        if text in {enum_value.name.lower(), str(enum_value.value).lower()}:
            return enum_value
    return None
