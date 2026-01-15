# MIDAS Model Summary

## Source Directory Structure

This document provides an overview of the `src` directory structure and the purpose of each subdirectory.

### Overview

The `src` directory contains the core application code organized into four main modules:
- `cli/` - Command-line interface and user interaction
- `config/` - Configuration management and data loading
- `models/` - Core domain models and business logic
- `types/` - Type definitions and data classes

---

## `src/cli/` - Command-Line Interface

The CLI module provides a menu-based command-line interface for interacting with the MIDAS application. It uses the Rich library for enhanced terminal output and user experience.

### `cli/cli.py`
Main entry point for the CLI application. Handles initialization, welcome messages, and starts the menu system.

### `cli/handlers/`
Contains command handlers that execute specific user actions:
- **`config_handlers.py`** - Handlers for configuration-related operations (viewing config values, facility types, system types, reloading configuration)
- **`simulate_handlers.py`** - Handlers for data simulation operations (generating data, viewing installations, facilities, systems, and examples)

### `cli/menu/`
Menu system components for building and managing interactive menus:
- **`menu_builder.py`** - Builder pattern for constructing menu configurations
- **`menu_config.py`** - Configuration classes for menu structure
- **`menu_factory.py`** - Factory functions that create pre-configured menus (main menu, configuration menu, simulate data menu)
- **`menu_handler.py`** - Core menu handler that displays menus and processes user selections
- **`menu_item.py`** - Menu item data structure representing individual menu options

### `cli/utils/`
Utility modules for CLI functionality:
- **`display.py`** - DisplayHelper class for consistent formatting of panels, tables, messages (info, error, success, warning)
- **`input.py`** - InputHelper class for user input collection (text, yes/no, choices, integers) with validation
- **`navigation.py`** - Navigation utilities for help text, progress indicators, and back command handling

---

## `src/config/` - Configuration Management

The config module handles loading and managing application configuration from Excel files and provides a singleton configuration class used throughout the application.

### `config/midas_config.py`
Main configuration class (`MIDASConfig`) that acts as a singleton storing:
- Facility types and system types loaded from Excel
- Application constants (thresholds, age limits, probabilities)
- Output/export configuration settings
- Initialization state and error tracking

### `config/functions/`
Functions for loading configuration data from Excel sheets:
- **`configure_logging.py`** - Sets up application logging configuration
- **`load_config_state_values_from_data.py`** - Loads general configuration parameters from the "Config" sheet
- **`load_facility_types_from_data.py`** - Loads facility type definitions from the "Facilities" sheet
- **`load_system_types_from_data.py`** - Loads system type definitions from the "Systems" sheet

### `config/midas_config_values.xlsx`
Excel file containing all configuration data (facility types, system types, and application parameters).

---

## `src/models/` - Domain Models

The models module contains the core domain models representing the MIDAS data structures and business logic.

### Core Models
- **`installation.py`** - `Installation` class representing an installation containing multiple facilities
- **`facility.py`** - `Facility` class representing a facility containing multiple systems
- **`system.py`** - `System` class representing individual systems within facilities
- **`condition_index.py`** - Logic for calculating condition indices from facilities and systems
- **`dependency_chain.py`** - `DependencyChain` class managing dependency relationships between systems

### `models/simulate_data/`
Module for generating simulated installation, facility, and system data:

- **`simulate_data.py`** - Main `SimulateData` class that generates simulated installations with facilities and systems, including probability distributions for condition indices, ages, and grades

- **`simulate_data_input_file.py`** - Handles loading and parsing input files for data simulation

- **`simulate_data_metadata.py`** - Metadata classes for tracking dataset information and generation parameters

- **`probability_distribution.py`** - `ProbabilityDistribution` class for defining and sampling from probability distributions

- **`probability_segment.py`** - `ProbabilitySegment` class representing segments within probability distributions

- **`simulate_data_output_file/`** - Output file generation and export system:
  - **`output_file.py`** - Main `SimulateDataOutputFile` class orchestrating data generation and export
  - **`config.py`** - `OutputConfig` class for configuring output file settings
  - **`enums.py`** - Enumerations for output formats (CSV, JSON, Excel), layouts (normalized/denormalized), and generation methods
  - **`generator.py`** - `DataGenerator` class for generating the actual data structures
  - **`transformers.py`** - `ModelTransformer` class for transforming domain models into exportable data structures
  - **`formatters/`** - Format-specific formatters:
    - **`base.py`** - Abstract base class for formatters
    - **`csv_formatter.py`** - CSV format exporter
    - **`excel_formatter.py`** - Excel format exporter with multiple sheets
    - **`json_formatter.py`** - JSON format exporter

---

## `src/types/` - Type Definitions

The types module contains data class definitions for type-safe configuration and domain objects.

- **`facility_type.py`** - `FacilityType` dataclass representing facility type configuration (key, title, life expectancy, mission criticality)
- **`system_type.py`** - `SystemType` dataclass representing system type configuration
- **`condition_index_record.py`** - `ConditionIndexRecord` dataclass for condition index data
- **`dependency_tier.py`** - `DependencyTier` enum/type for dependency tier classifications
- **`ufc_grade.py`** - `UFCGrade` enum/type for UFC (Unified Facilities Criteria) grade classifications

These types are used throughout the application for type safety and are loaded from the configuration Excel file on startup.
