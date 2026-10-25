"""Structured logging configuration with JSON output and request_id support."""

from __future__ import annotations

import logging
import logging.config
import sys


def setup_logging(level: str = "INFO", log_format: str = "json") -> None:
    """Configure structured logging for the application.

    Args:
        level: Log level string (DEBUG, INFO, WARNING, ERROR).
        log_format: 'json' for production structured logs, 'console' for dev.
    """
    config = _json_logging_config(level) if log_format == "json" else _console_logging_config(level)

    logging.config.dictConfig(config)
    logging.captureWarnings(True)


def _json_logging_config(level: str) -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {
                "()": "backend.core.logging.formatter.JSONFormatter",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": sys.stdout,
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
        "loggers": {
            "uvicorn.access": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "handlers": ["console"],
                "level": "WARNING",
                "propagate": False,
            },
        },
    }


def _console_logging_config(level: str) -> dict:
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "console": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "console",
                "stream": sys.stdout,
            },
        },
        "root": {
            "level": level,
            "handlers": ["console"],
        },
    }
