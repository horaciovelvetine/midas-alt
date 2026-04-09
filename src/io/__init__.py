"""MIDAS file input/output package."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "ConfigWorkbookLoadError",
    "ConfigWorkbookLoader",
    "DataExporter",
    "DataTransformer",
    "ExportConfig",
    "OutputFileType",
    "OutputLayoutSchema",
    "SimulationDataLoader",
]

_EXPORTS = {
    "ConfigWorkbookLoadError": ("src.io.loaders", "ConfigWorkbookLoadError"),
    "ConfigWorkbookLoader": ("src.io.loaders", "ConfigWorkbookLoader"),
    "DataExporter": ("src.io.models", "DataExporter"),
    "DataTransformer": ("src.io.models", "DataTransformer"),
    "ExportConfig": ("src.io.models", "ExportConfig"),
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
