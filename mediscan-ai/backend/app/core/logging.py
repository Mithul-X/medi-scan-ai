"""
Structured logging setup.

Logs as single-line JSON so they're greppable on Render's log viewer
(no log aggregation service needed — stays inside the free-tier constraint).
"""

import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings


class JSONFormatter(logging.Formatter):
    """Renders each log record as one JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach any extra fields passed via `logger.info(msg, extra={...})`
        reserved = set(logging.LogRecord(
            "", 0, "", 0, "", None, None
        ).__dict__.keys()) | {"message", "asctime"}
        for key, value in record.__dict__.items():
            if key not in reserved:
                payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def configure_logging() -> None:
    """Call once at startup (see app/main.py lifespan)."""
    settings = get_settings()

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    # Avoid duplicate handlers if configure_logging() is called more than once
    # (e.g. under pytest with multiple app instances).
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
