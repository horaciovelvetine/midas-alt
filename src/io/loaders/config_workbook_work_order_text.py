"""Work Order Text sheet parsing for the MIDAS configuration workbook."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd
from pandas import ExcelFile

from src.models import WorkOrderText

logger = logging.getLogger(__name__)


def _is_matching_text_header(value: Any) -> bool:
    """Return whether the header cell looks like a work-order text column."""
    return isinstance(value, str) and "description" in value.strip().lower()


def _resolve_work_order_text_column_bounds(
    title_row: list[Any],
    second_header_row: list[Any],
    system_type: str | None,
) -> tuple[int, int, int] | None:
    """Resolve description/request/action column indices for a system block."""
    if not system_type:
        return None

    normalized = system_type.strip().lower()
    candidate_indices = [
        idx
        for idx, value in enumerate(title_row)
        if isinstance(value, str) and value.strip().lower() == normalized
    ]
    if not candidate_indices:
        return None

    for idx in candidate_indices:
        for start in (idx - 1, idx, idx + 1):
            if start < 0 or start + 2 >= len(second_header_row):
                continue
            if _is_matching_text_header(second_header_row[start]):
                return (start, start + 1, start + 2)

    first = candidate_indices[0]
    if first + 2 < len(second_header_row):
        return (first, first + 1, first + 2)
    return None


def _load_work_order_text_cache(
    excel_file: ExcelFile,
) -> dict[str, list[WorkOrderText]]:
    """Eagerly load work-order text samples grouped by system type title."""
    if "Work Order Text" not in excel_file.sheet_names:
        return {}

    try:
        header_df = pd.read_excel(
            excel_file, sheet_name="Work Order Text", header=None, nrows=2
        )
    except Exception as exc:  # pragma: no cover - defensive around workbook parsing
        logger.warning("Failed loading Work Order Text headers: %s", exc)
        return {}

    if header_df.empty or len(header_df.index) < 2:
        return {}

    title_row = header_df.iloc[0].tolist()
    second_header_row = header_df.iloc[1].tolist()

    try:
        body_df = pd.read_excel(
            excel_file, sheet_name="Work Order Text", header=None, skiprows=2
        )
    except Exception as exc:  # pragma: no cover - defensive around workbook parsing
        logger.warning("Failed loading Work Order Text body: %s", exc)
        return {}

    if body_df.empty:
        return {}

    triplet_map: dict[str, tuple[int, int, int]] = {}
    fallback_triplet: tuple[int, int, int] | None = None
    seen_titles: set[str] = set()

    for cell in title_row:
        if not isinstance(cell, str) or not cell.strip():
            continue
        normalized = cell.strip().lower()
        if normalized in seen_titles:
            continue
        bounds = _resolve_work_order_text_column_bounds(
            title_row, second_header_row, cell.strip()
        )
        if bounds is not None:
            triplet_map[normalized] = bounds
            seen_titles.add(normalized)

    if not triplet_map:
        for start in range(len(second_header_row) - 2):
            if _is_matching_text_header(second_header_row[start]):
                fallback_triplet = (start, start + 1, start + 2)
                break
    else:
        fallback_triplet = next(iter(triplet_map.values()))

    def _extract_rows(cols: tuple[int, int, int]) -> list[WorkOrderText]:
        rows: list[WorkOrderText] = []
        for _, row in body_df.iterrows():
            values: list[str] = []
            for column_index in cols:
                if column_index < len(row):
                    value = row.iloc[column_index]
                    values.append(
                        str(value).strip()
                        if isinstance(value, str) and value.strip()
                        else "example text"
                    )
                else:
                    values.append("example text")
            while len(values) < 3:
                values.append("example text")
            rows.append(
                WorkOrderText(
                    problem_description=values[0],
                    requested_action=values[1],
                    action_taken=values[2],
                )
            )
        return rows

    cache: dict[str, list[WorkOrderText]] = {}
    for title_key, cols in triplet_map.items():
        extracted = _extract_rows(cols)
        if extracted:
            cache[title_key] = extracted

    if fallback_triplet is not None:
        extracted = _extract_rows(fallback_triplet)
        if extracted:
            cache.setdefault("_fallback", extracted)

    logger.info("Loaded work-order text cache with %s system-type groups", len(cache))
    return cache
