"""Work Orders sheet loader for the MIDAS configuration workbook.

Parses the seven-column ``Work Orders`` sheet (``Trade``, ``Work Category``,
``System``, ``Priority Code``, ``Description``, ``Requested Actions``,
``Actions Taken``) into :class:`~src.models.domain.work_order_text.WorkOrderText`
samples grouped by normalized system title. A pooled ``"_fallback"`` bucket
holds every parsed row so the generator can still sample when a system title
has no exact match.
"""

from __future__ import annotations

import logging
import re
from typing import Any

import pandas as pd
from pandas import ExcelFile

from src.config.midas_settings import MidasSettings
from src.io.loaders.midas_config_data_loader import ConfigDataLoadResult
from src.models import WorkOrderText

logger = logging.getLogger(__name__)

FALLBACK_KEY = "_fallback"

_SHEET_NAME = "Work Orders"
_REQUIRED_COLUMNS = (
    "Trade",
    "Work Category",
    "System",
    "Priority Code",
    "Description",
    "Requested Actions",
    "Actions Taken",
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize_system_title(value: Any) -> str:
    """Return a lowercase, alphanumeric-only form of ``value`` for keying."""
    if value is None:
        return ""
    text = str(value).strip().lower()
    return _NON_ALNUM_RE.sub("", text)


def load_work_order_text_config_data(
    excel_file: ExcelFile, result: ConfigDataLoadResult
) -> dict[str, list[WorkOrderText]]:
    """Load work-order templates grouped by normalized system title."""
    if _SHEET_NAME not in excel_file.sheet_names:
        result.add_warning(
            f"Unable to find the '{_SHEET_NAME}' sheet in the "
            f"{MidasSettings.DEFAULT_CONFIG_DATA_FILENAME} excel file."
        )
        return {}

    try:
        df = pd.read_excel(excel_file, sheet_name=_SHEET_NAME)
    except Exception as exc:  # pragma: no cover - defensive around workbook parsing
        logger.warning("Failed loading '%s' sheet: %s", _SHEET_NAME, exc)
        result.add_warning(f"Failed loading '{_SHEET_NAME}' sheet: {exc}")
        return {}

    if df.empty:
        result.add_warning(f"'{_SHEET_NAME}' sheet contained no rows.")
        return {}

    missing_columns = [name for name in _REQUIRED_COLUMNS if name not in df.columns]
    if missing_columns:
        result.add_warning(
            f"'{_SHEET_NAME}' sheet is missing required column(s): "
            f"{', '.join(missing_columns)}."
        )
        return {}

    cache: dict[str, list[WorkOrderText]] = {}
    fallback: list[WorkOrderText] = []
    skipped = 0

    for _, row in df.iterrows():
        template = _row_to_template(row)
        if template is None:
            skipped += 1
            continue
        key = normalize_system_title(template.system_title)
        if not key:
            skipped += 1
            continue
        cache.setdefault(key, []).append(template)
        fallback.append(template)

    if fallback:
        cache[FALLBACK_KEY] = fallback

    if skipped:
        logger.info(
            "Skipped %s '%s' row(s) missing required values", skipped, _SHEET_NAME
        )
    logger.info(
        "Loaded %s work-order template(s) across %s system group(s) from '%s'",
        len(fallback),
        max(0, len(cache) - (1 if FALLBACK_KEY in cache else 0)),
        _SHEET_NAME,
    )
    return cache


def _row_to_template(row: pd.Series) -> WorkOrderText | None:
    """Coerce a workbook row into a :class:`WorkOrderText` or ``None`` if unusable."""
    system_title = _clean_text(row.get("System"))
    if not system_title:
        return None

    problem_description = _clean_text(row.get("Description"))
    requested_action = _clean_text(row.get("Requested Actions"))
    action_taken = _clean_text(row.get("Actions Taken"))
    if not (problem_description or requested_action or action_taken):
        return None

    return WorkOrderText(
        system_title=system_title,
        trade=_clean_text(row.get("Trade")) or "",
        work_category=_clean_text(row.get("Work Category")) or "",
        priority_code=_coerce_priority_code(row.get("Priority Code")),
        problem_description=problem_description or "",
        requested_action=requested_action or "",
        action_taken=action_taken or "",
    )


def _clean_text(value: Any) -> str:
    """Return a stripped string form of ``value`` (empty if NaN/None)."""
    if value is None:
        return ""
    if isinstance(value, float) and pd.isna(value):
        return ""
    text = str(value).strip()
    return text


def _coerce_priority_code(value: Any) -> int | None:
    """Parse the priority-code cell into an int, returning ``None`` when blank."""
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None
