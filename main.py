"""Main entry point for MIDAS application."""

from src.cli.cli import run_cli
from src.config import configure_logging


def main():
    """Initialize logging and start the CLI."""
    configure_logging()
    run_cli()


if __name__ == "__main__":
    main()
