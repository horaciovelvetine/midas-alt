import logging
import os
import sys


def configure_logging() -> None:
    """Configure logging for the application."""
    # Get log level from environment variable, default to INFO
    log_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    log_level = getattr(logging, log_level_name, logging.INFO)

    # Create custom formatter that shows only last traceback line
    formatter = logging.Formatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%H:%M:%S",
    )

    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = []  # Clear existing handlers
    root_logger.addHandler(console_handler)

    # Reduce noise from third-party libraries
    logging.getLogger("pandas").setLevel(logging.WARNING)
    logging.getLogger("openpyxl").setLevel(logging.WARNING)
