"""Export destination formats for dataset writers."""

from enum import Enum


class OutputFileType(Enum):
    """CSV or Excel workbook output."""

    CSV = "csv"
    XLSX = "xlsx"
