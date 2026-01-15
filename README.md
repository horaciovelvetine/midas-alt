# MIDAS

MIDAS is a Python application for simulating and managing installation, facility, and system data. It provides a menu-based CLI interface for generating simulated data, viewing configurations, and managing installations with their associated facilities and systems.

## Prerequisites

- **Python 3.11+**
- **[uv](https://github.com/astral-sh/uv)** - Fast Python package installer and resolver

### Installing uv

If you don't have `uv` installed, follow the [official installation guide](https://github.com/astral-sh/uv?tab=readme-ov-file#installation):

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

## Getting Started

### 1. Clone the Repository

```bash
git clone <repository-url>
cd midas-alt
```

### 2. Set Up the Development Environment

```bash
# Create virtual environment
uv venv

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies (uv handles this automatically when using uv run)
# Dependencies are managed in pyproject.toml
```

### 3. Run the Application

```bash
uv run python main.py
```

The application will:
- Load configuration from `src/config/midas_config_values.xlsx`
- Display a welcome message
- Present an interactive menu system for navigation

## Development Workflow

### Running Tests

```bash
# Run all tests with coverage
uv run pytest

# Run tests in verbose mode
uv run pytest -v
```

### Code Quality

```bash
# Check for linting errors
uv run ruff check .

# Auto-fix linting issues
uv run ruff check . --fix

# Format code
uv run ruff format .

# Format docstrings (optional)
uv run docformatter --in-place --recursive .
```