"""Application logging.

Railway classifies anything a container writes to **stderr** as `level.error`,
regardless of what the record itself says. A bare `logging.StreamHandler()`
defaults to stderr, so every `INFO` line the app produced arrived in the log
explorer coloured red — which buried genuine failures in routine chatter.

Logs therefore go to stdout, and in production they are emitted as single-line
JSON: Railway reads `message` as the log text and `level` as the severity, and
exposes every other key as an attribute you can filter on with `@name:value`.
Development keeps the human-readable format for the console and `dev.log`.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime

from app.config import Settings

LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
LOG_FILE = "dev.log"

# Railway's severities. `critical` has no counterpart, so it maps to the most
# severe level the log explorer understands.
RAILWAY_LEVELS = {
    "DEBUG": "debug",
    "INFO": "info",
    "WARNING": "warn",
    "ERROR": "error",
    "CRITICAL": "error",
}

# These log one INFO line per outbound request, so a single Clerk lookup or
# GitHub call is a log line we did not ask for. Our own request-level logging
# is unaffected.
NOISY_LOGGERS = ("httpx", "httpcore")

# Uvicorn installs its own handlers at boot — before our lifespan hook runs —
# and sets propagate=False, so clearing the root logger's handlers does not
# reach them. `uvicorn.error` writes to stderr, which is the same trap again.
UVICORN_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")


class JsonFormatter(logging.Formatter):
    """Render a record as one JSON line in Railway's field contract."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "message": record.getMessage(),
            "level": RAILWAY_LEVELS.get(record.levelname, "info"),
            "logger": record.name,
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def configure_logging(settings: Settings, log_dir: str = "logs") -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.handlers.clear()

    is_development = settings.environment == "development"
    text_formatter = logging.Formatter(LOG_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(text_formatter if is_development else JsonFormatter())
    root.addHandler(console)

    if is_development:
        os.makedirs(log_dir, exist_ok=True)
        file_handler = logging.FileHandler(os.path.join(log_dir, LOG_FILE), mode="w")
        file_handler.setFormatter(text_formatter)
        root.addHandler(file_handler)

    for name in NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

    # Hand uvicorn's output to the root handler so the whole process emits one
    # consistent stream instead of three differently-formatted ones.
    for name in UVICORN_LOGGERS:
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
