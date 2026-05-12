"""MIDAS file input/output package."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "ConfigDataLoadResult",
    "ConfigWorkbookLoadError",
    "DataExporter",
    "DataTransformer",
    "ExportConfig",
    "MidasConfigDataLoader",
    "OutputFileType",
    "OutputLayoutSchema",
    "SimulationDataLoader",
]

_EXPORTS = {
    "ConfigDataLoadResult": ("src.io.loaders", "ConfigDataLoadResult"),
    "ConfigWorkbookLoadError": ("src.io.loaders", "ConfigWorkbookLoadError"),
    "DataExporter": ("src.io.models", "DataExporter"),
    "DataTransformer": ("src.io.models", "DataTransformer"),
    "ExportConfig": ("src.io.models", "ExportConfig"),
    "MidasConfigDataLoader": ("src.io.loaders", "MidasConfigDataLoader"),
    "OutputFileType": ("src.io.enums", "OutputFileType"),
    "OutputLayoutSchema": ("src.io.enums", "OutputLayoutSchema"),
    "SimulationDataLoader": ("src.io.loaders", "SimulationDataLoader"),
}


def __getattr__(name: str):
    """Lazily resolve public IO exports to avoid package import cycles."""
    if name not in _EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = _EXPORTS[name]
    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value
