"""Logging utilities for the reporting engine."""

import logging
from pathlib import Path
from typing import Optional

# Default log directory anchored to the project root so the log file always
# lands in <project>/logs regardless of the current working directory.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"


def setup_logger(
    name: str = "reporting_engine",
    log_dir: Optional[str] = None,
    log_file: str = "application.log",
) -> logging.Logger:
    """Set up a logger with file and console output."""
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    log_path = Path(log_dir) if log_dir is not None else DEFAULT_LOG_DIR
    log_path.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(log_path / log_file)
    file_handler.setLevel(logging.DEBUG)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    return logger
