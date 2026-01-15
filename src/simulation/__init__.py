"""Simulation module for generating and exporting synthetic data."""

from .distributions import ProbabilityDistribution, ProbabilitySegment
from .export import DataExporter, DataTransformer, ExportConfig, OutputFormat, OutputLayout
from .generator import DataGenerator, DegradationPattern, SimulationConfig

__all__ = [
    # Distributions
    "ProbabilityDistribution",
    "ProbabilitySegment",
    # Generator
    "DataGenerator",
    "SimulationConfig",
    "DegradationPattern",
    # Export
    "DataExporter",
    "ExportConfig",
    "DataTransformer",
    "OutputFormat",
    "OutputLayout",
]
