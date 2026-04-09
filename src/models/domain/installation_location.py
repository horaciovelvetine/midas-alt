"""Reference row for labeling generated installations (place and coordinates)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class InstallationLocation:
    """Workbook-defined place name, region, and coordinates string."""

    title: str
    location: str
    region: str
    coordinates: str
