"""CLI command handlers."""

from .config_handlers import (
    handle_reload_configuration,
    handle_view_config_values,
    handle_view_facility_types_summary,
    handle_view_system_types_summary,
)
from .ml_handlers import (
    handle_create_training_dataset,
    handle_make_predictions,
    handle_train_and_compare_models,
    handle_view_features,
)
from .simulate_handlers import (
    handle_generate_data,
    handle_quick_generate,
    handle_view_facility_and_system,
    handle_view_installation_interactive,
    handle_view_simulated_data_examples,
)

__all__ = [
    # Config handlers
    "handle_reload_configuration",
    "handle_view_config_values",
    "handle_view_facility_types_summary",
    "handle_view_system_types_summary",
    # ML handlers
    "handle_create_training_dataset",
    "handle_make_predictions",
    "handle_train_and_compare_models",
    "handle_view_features",
    # Simulate handlers
    "handle_generate_data",
    "handle_quick_generate",
    "handle_view_facility_and_system",
    "handle_view_installation_interactive",
    "handle_view_simulated_data_examples",
]
