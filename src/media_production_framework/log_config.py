"""
Logging configuration for the framework.
"""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Configure root logging and return the framework logger."""

    normalized_level = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(
        level=normalized_level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    return logging.getLogger("media_production_framework")
