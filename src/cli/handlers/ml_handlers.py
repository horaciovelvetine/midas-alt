"""ML prediction command handlers."""

import logging
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from src.cli.utils import DisplayHelper, InputHelper, NavigationHelper
from src.config import MIDASSettings
from src.config.app_state import get_app_state
from src.domain import Facility, System
from src.prediction import (
    DatasetConfig,
    DegradationFeatures,
    ExponentialDecayModel,
    FeatureExtractor,
    LabelType,
    ModelEvaluator,
    SklearnRegressionModel,
    TrainingDataGenerator,
)
from src.simulation import DataGenerator

logger = logging.getLogger(__name__)
console = Console()


def _get_settings() -> MIDASSettings:
    """Get settings from the application state."""
    return get_app_state().settings


def _format_feature_value(value) -> str:
    """Format a feature value for display."""
    if value is None:
        return "[dim]None[/dim]"
    elif isinstance(value, float):
        return f"{value:.4f}"
    elif isinstance(value, int):
        return str(value)
    else:
        return str(value)


def _get_feature_description(name: str) -> str:
    """Get human-readable description for a feature."""
    descriptions = {
        "entity_id": "Unique identifier for the entity",
        "entity_type": "Type of entity (facility or system)",
        "snapshot_timestamp": "When the features were extracted",
        "condition_index": "Current condition index (0-100)",
        "age_months": "Age of the entity in months",
        "life_expectancy_months": "Expected lifespan in months",
        "facility_type_key": "Facility type identifier",
        "system_type_key": "System type identifier",
        "mission_criticality": "How critical to mission (1-5)",
        "resiliency_grade": "UFC resiliency grade (1-4)",
        "dependency_tier": "Dependency chain tier",
        "dependency_group_count": "Number of dependency groups",
        "remaining_life_ratio": "Remaining life / total life",
        "condition_age_ratio": "Condition index / age ratio",
        "condition_index_lag_3mo": "CI from 3 months ago",
        "condition_index_lag_6mo": "CI from 6 months ago",
        "condition_index_lag_12mo": "CI from 12 months ago",
        "ci_delta_3mo": "CI change over 3 months",
        "ci_delta_12mo": "CI change over 12 months",
    }
    return descriptions.get(name, "")


def handle_view_features() -> None:
    """View feature extraction for a sample entity."""
    DisplayHelper.clear_screen()
    
    console.print("\n[bold cyan]Feature Extraction Demo[/bold cyan]\n")
    console.print("This shows what features are extracted from entities for ML prediction.\n")
    
    # Ask which entity type to view
    entity_type = InputHelper.ask_choice(
        "Select entity type to view features for",
        choices=["facility", "system"],
        default="facility",
        allow_back=True,
    )
    
    if entity_type is None:
        return
    
    settings = _get_settings()
    generator = DataGenerator(settings=settings)
    extractor = FeatureExtractor(settings)
    
    # Generate sample data
    console.print("\n[dim]Generating sample entity...[/dim]")
    installation, facilities, systems = generator.generate_installation()
    
    if entity_type == "facility" and facilities:
        entity = facilities[0]
        features = extractor.extract_facility_features(entity)
        entity_name = settings.get_facility_type(entity.facility_type_key or 0)
        title = f"Features for Facility: {entity_name.title if entity_name else 'Unknown'}"
    elif entity_type == "system" and systems:
        entity = systems[0]
        features = extractor.extract_system_features(entity)
        entity_name = settings.get_system_type(entity.system_type_key or 0)
        title = f"Features for System: {entity_name.title if entity_name else 'Unknown'}"
    else:
        DisplayHelper.print_warning("No entities generated.")
        InputHelper.wait_for_continue()
        return
    
    # Create feature table
    table = Table(
        title=title,
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Feature", style="cyan", width=25)
    table.add_column("Value", style="green", width=20, justify="right")
    table.add_column("Description", style="dim", width=35)
    
    # Get all feature fields from the dataclass
    feature_dict = {
        "condition_index": features.condition_index,
        "age_months": features.age_months,
        "life_expectancy_months": features.life_expectancy_months,
        "facility_type_key": features.facility_type_key,
        "system_type_key": features.system_type_key,
        "mission_criticality": features.mission_criticality,
        "resiliency_grade": features.resiliency_grade,
        "dependency_tier": features.dependency_tier,
        "dependency_group_count": features.dependency_group_count,
        "remaining_life_ratio": features.remaining_life_ratio,
        "condition_age_ratio": features.condition_age_ratio,
    }
    
    # Add lag features if available
    if features.condition_index_lag_3mo is not None:
        feature_dict["condition_index_lag_3mo"] = features.condition_index_lag_3mo
    if features.condition_index_lag_6mo is not None:
        feature_dict["condition_index_lag_6mo"] = features.condition_index_lag_6mo
    if features.condition_index_lag_12mo is not None:
        feature_dict["condition_index_lag_12mo"] = features.condition_index_lag_12mo
    if features.ci_delta_3mo is not None:
        feature_dict["ci_delta_3mo"] = features.ci_delta_3mo
    if features.ci_delta_12mo is not None:
        feature_dict["ci_delta_12mo"] = features.ci_delta_12mo
    
    for name, value in feature_dict.items():
        table.add_row(
            name,
            _format_feature_value(value),
            _get_feature_description(name),
        )
    
    DisplayHelper.print_table(table)
    
    # Show interpretation
    console.print("[bold]Interpretation:[/bold]")
    ci = features.condition_index
    age = features.age_months
    remaining = features.remaining_life_ratio
    
    if ci >= 70:
        status = "[green]Good condition[/green]"
    elif ci >= 50:
        status = "[yellow]Fair condition[/yellow]"
    elif ci >= 25:
        status = "[orange3]Poor condition[/orange3]"
    else:
        status = "[red]Critical condition[/red]"
    
    console.print(f"  Status: {status} (CI: {ci:.1f})")
    console.print(f"  Age: {age // 12} years, {age % 12} months")
    console.print(f"  Remaining life: {remaining * 100:.1f}%")
    
    InputHelper.wait_for_continue()


def handle_create_training_dataset() -> None:
    """Create a training dataset for ML models."""
    DisplayHelper.clear_screen()
    
    console.print("\n[bold cyan]Create Training Dataset[/bold cyan]\n")
    console.print("Generate labeled data for training degradation prediction models.\n")
    
    # Get entity type
    entity_type = InputHelper.ask_choice(
        "Select entity type",
        choices=["facility", "system", "both"],
        default="facility",
        allow_back=True,
    )
    if entity_type is None:
        return
    
    # Get sample count
    sample_count = InputHelper.ask_number(
        "Number of samples to generate",
        min_value=10,
        max_value=10000,
        default=500,
        allow_back=True,
    )
    if sample_count is None:
        return
    
    # Get label type
    console.print("\n[bold]Label Types:[/bold]")
    console.print("  [cyan]1[/cyan] - Months to degradation (regression)")
    console.print("  [cyan]2[/cyan] - Degradation rate (regression)")
    console.print("  [cyan]3[/cyan] - Will degrade within timeframe (classification)")
    
    label_choice = InputHelper.ask_choice(
        "Select label type",
        choices=["1", "2", "3"],
        default="1",
        allow_back=True,
    )
    if label_choice is None:
        return
    
    label_type_map = {
        "1": LabelType.MONTHS_TO_DEGRADATION,
        "2": LabelType.DEGRADATION_RATE,
        "3": LabelType.WILL_DEGRADE_IN_MONTHS,
    }
    label_type = label_type_map[label_choice]
    
    # Generate the dataset
    settings = _get_settings()
    
    # Configure dataset generation - n_installations affects sample count
    # Each installation generates multiple facilities/systems
    n_installations = max(1, sample_count // 10)  # Rough estimate
    
    config = DatasetConfig(
        n_installations=n_installations,
        label_type=label_type,
        seed=42,
    )
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task(f"Generating samples...", total=None)
        
        data_gen = TrainingDataGenerator(settings=settings, config=config)
        
        if entity_type == "facility":
            X, y = data_gen.generate_facility_dataset()
        elif entity_type == "system":
            X, y = data_gen.generate_system_dataset()
        else:  # both
            X, y = data_gen.generate()
        
        progress.update(task, completed=True)
    
    # Show summary
    console.print("\n[bold green]Dataset Created Successfully![/bold green]\n")
    
    summary_table = Table(title="Dataset Summary", show_header=True, header_style="bold cyan")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green", justify="right")
    
    summary_table.add_row("Total samples", str(len(X)))
    summary_table.add_row("Feature columns", str(len(X.columns)))
    summary_table.add_row("Label type", label_type.value)
    summary_table.add_row("Label min", f"{y.min():.2f}")
    summary_table.add_row("Label max", f"{y.max():.2f}")
    summary_table.add_row("Label mean", f"{y.mean():.2f}")
    summary_table.add_row("Label std", f"{y.std():.2f}")
    
    DisplayHelper.print_table(summary_table)
    
    # Show feature columns
    console.print("[bold]Feature Columns:[/bold]")
    cols_per_row = 4
    cols = list(X.columns)
    for i in range(0, len(cols), cols_per_row):
        row_cols = cols[i:i + cols_per_row]
        console.print("  " + ", ".join(f"[cyan]{c}[/cyan]" for c in row_cols))
    
    # Option to export
    console.print()
    if InputHelper.ask_yes_no("Export dataset to CSV?", default=False, allow_back=False):
        export_path = Path(".") / f"training_dataset_{entity_type}_{sample_count}.csv"
        
        # Combine features and labels
        export_df = X.copy()
        export_df["label"] = y
        export_df.to_csv(export_path, index=False)
        
        DisplayHelper.print_success(f"Dataset exported to: {export_path}")
    
    InputHelper.wait_for_continue()


def handle_train_and_compare_models() -> None:
    """Train and compare multiple ML models."""
    DisplayHelper.clear_screen()
    
    console.print("\n[bold cyan]Train & Compare Models[/bold cyan]\n")
    console.print("Train multiple degradation prediction models and compare performance.\n")
    
    # Get sample count for training
    sample_count = InputHelper.ask_number(
        "Number of training samples",
        min_value=100,
        max_value=5000,
        default=500,
        allow_back=True,
    )
    if sample_count is None:
        return
    
    settings = _get_settings()
    
    # Configure dataset generation
    n_installations = max(1, sample_count // 10)
    config = DatasetConfig(
        n_installations=n_installations,
        label_type=LabelType.MONTHS_TO_DEGRADATION,
        seed=42,
    )
    
    # Generate training data
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating training data...", total=None)
        
        data_gen = TrainingDataGenerator(settings=settings, config=config)
        X, y = data_gen.generate_facility_dataset()
        
        progress.update(task, description="Training data generated!", completed=True)
    
    console.print(f"\n[dim]Generated {len(X)} samples with {len(X.columns)} features[/dim]\n")
    
    # Define models to train
    models = [
        ExponentialDecayModel(),
        SklearnRegressionModel("ridge"),
        SklearnRegressionModel("random_forest"),
        SklearnRegressionModel("gradient_boosting"),
    ]
    
    # Train and evaluate models
    console.print("[bold]Training models...[/bold]\n")
    
    evaluator = ModelEvaluator(test_size=0.2, random_state=42)
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Evaluating models...", total=len(models))
        
        results_df = evaluator.compare_models(models, X, y)
        
        progress.update(task, completed=len(models))
    
    # Display results
    console.print("\n[bold green]Model Comparison Results[/bold green]\n")
    
    results_table = Table(
        title="Performance Metrics (lower MAE/RMSE better, higher R2/accuracy better)",
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
    )
    results_table.add_column("Model", style="cyan", width=25)
    results_table.add_column("MAE", justify="right", width=12)
    results_table.add_column("RMSE", justify="right", width=12)
    results_table.add_column("R2", justify="right", width=10)
    results_table.add_column("Within 6mo", justify="right", width=12)
    results_table.add_column("Within 12mo", justify="right", width=12)
    
    # Find best model by MAE
    best_idx = results_df["mae"].idxmin()
    
    for idx, row in results_df.iterrows():
        model_name = idx
        is_best = idx == best_idx
        
        # Style best model
        if is_best:
            model_name = f"[bold green]{model_name} *[/bold green]"
            style = "green"
        else:
            style = "white"
        
        results_table.add_row(
            model_name,
            f"[{style}]{row['mae']:.2f}[/{style}]",
            f"[{style}]{row['rmse']:.2f}[/{style}]",
            f"[{style}]{row['r2']:.4f}[/{style}]",
            f"[{style}]{row['within_6mo'] * 100:.1f}%[/{style}]",
            f"[{style}]{row['within_12mo'] * 100:.1f}%[/{style}]",
        )
    
    DisplayHelper.print_table(results_table)
    
    console.print("[dim]* Best model (lowest MAE)[/dim]")
    console.print(f"\n[bold]Best Model:[/bold] [green]{best_idx}[/green]")
    console.print(f"  Mean Absolute Error: {results_df.loc[best_idx, 'mae']:.2f} months")
    console.print(f"  Predictions within 12 months: {results_df.loc[best_idx, 'within_12mo'] * 100:.1f}%")
    
    # Show feature importance for random forest
    rf_model = next((m for m in models if m.name == "sklearn_random_forest"), None)
    if rf_model and hasattr(rf_model, "_model") and rf_model._model is not None:
        console.print("\n[bold]Feature Importance (Random Forest):[/bold]")
        
        try:
            importances = rf_model._model.feature_importances_
            feature_names = rf_model._feature_names
            
            # Sort by importance
            sorted_idx = importances.argsort()[::-1][:8]  # Top 8
            
            for i, idx in enumerate(sorted_idx):
                bar_len = int(importances[idx] * 40)
                bar = "█" * bar_len
                console.print(f"  {feature_names[idx]:25} {bar} {importances[idx]:.4f}")
        except Exception:
            pass
    
    InputHelper.wait_for_continue()


def handle_make_predictions() -> None:
    """Make predictions on sample entities."""
    DisplayHelper.clear_screen()
    
    console.print("\n[bold cyan]Make Degradation Predictions[/bold cyan]\n")
    console.print("Generate sample entities and predict time to degradation.\n")
    
    # Get number of entities
    entity_count = InputHelper.ask_number(
        "Number of entities to predict",
        min_value=1,
        max_value=20,
        default=5,
        allow_back=True,
    )
    if entity_count is None:
        return
    
    settings = _get_settings()
    generator = DataGenerator(settings=settings)
    extractor = FeatureExtractor(settings)
    
    # Train a quick model
    console.print("\n[dim]Training prediction model...[/dim]")
    
    config = DatasetConfig(
        n_installations=30,  # ~300 samples
        label_type=LabelType.MONTHS_TO_DEGRADATION,
        seed=42,
    )
    data_gen = TrainingDataGenerator(settings=settings, config=config)
    X_train, y_train = data_gen.generate_facility_dataset()
    
    # Use random forest for predictions with uncertainty
    model = SklearnRegressionModel("random_forest")
    model.fit(X_train, y_train)
    
    console.print("[dim]Model trained. Generating predictions...[/dim]\n")
    
    # Generate entities and predict
    installation, facilities, systems = generator.generate_installation()
    
    # Use first N facilities
    entities = facilities[:entity_count]
    
    # Create predictions table
    table = Table(
        title="Degradation Predictions",
        show_header=True,
        header_style="bold cyan",
        show_lines=True,
    )
    table.add_column("Facility", style="cyan", width=20)
    table.add_column("Current CI", justify="right", width=12)
    table.add_column("Age (yrs)", justify="right", width=10)
    table.add_column("Prediction", justify="center", width=20)
    table.add_column("Confidence", justify="center", width=20)
    table.add_column("Status", width=15)
    
    for entity in entities:
        # Extract features
        features = extractor.extract_facility_features(entity)
        feature_df = extractor.features_to_dataframe([features])
        
        # Make prediction with uncertainty
        predictions = model.predict_with_uncertainty(feature_df, confidence=0.8)
        pred = predictions[0]
        
        # Get entity info
        facility_type = settings.get_facility_type(entity.facility_type_key or 0)
        name = facility_type.title[:18] if facility_type else "Unknown"
        ci = entity.condition_index or 0
        age_years = (entity.age_years or 0)
        
        # Format prediction
        months = pred.value
        years = months / 12
        pred_str = f"{years:.1f} years ({months:.0f} mo)"
        
        # Format confidence interval
        low_years = pred.lower_bound / 12 if pred.lower_bound else 0
        high_years = pred.upper_bound / 12 if pred.upper_bound else 0
        conf_str = f"{low_years:.1f} - {high_years:.1f} years"
        
        # Determine status
        if months <= 12:
            status = "[red]Urgent[/red]"
        elif months <= 36:
            status = "[orange3]Soon[/orange3]"
        elif months <= 60:
            status = "[yellow]Monitor[/yellow]"
        else:
            status = "[green]Good[/green]"
        
        table.add_row(
            name,
            f"{ci:.1f}",
            f"{age_years}",
            pred_str,
            conf_str,
            status,
        )
    
    DisplayHelper.print_table(table)
    
    # Show legend
    console.print("[bold]Status Legend:[/bold]")
    console.print("  [red]Urgent[/red]     - Predicted degradation within 1 year")
    console.print("  [orange3]Soon[/orange3]       - Predicted degradation within 3 years")
    console.print("  [yellow]Monitor[/yellow]    - Predicted degradation within 5 years")
    console.print("  [green]Good[/green]       - Predicted degradation beyond 5 years")
    
    console.print("\n[dim]Note: Predictions are based on simulated data and model training.[/dim]")
    console.print("[dim]Confidence intervals show 80% prediction bounds.[/dim]")
    
    InputHelper.wait_for_continue()
