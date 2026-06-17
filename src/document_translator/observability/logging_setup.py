from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from document_translator.config.settings import PipelineConfig

LOGGER_NAME = "document_translator"


def get_logger(name: str | None = None) -> logging.Logger:
    logger = logging.getLogger(name or LOGGER_NAME)
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("job_id", "source_file", "issue_code", "stage", "scope", "progress", "status"):
            if hasattr(record, key):
                value = getattr(record, key)
                if value is not None:
                    payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(config: PipelineConfig) -> logging.Logger:
    logger = get_logger()
    logger.handlers.clear()
    logger.setLevel(_resolve_level(config.log_level))
    logger.propagate = False

    handler = logging.StreamHandler(sys.stderr)
    if config.log_format == "json":
        handler.setFormatter(JsonLogFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
    logger.addHandler(handler)
    return logger


def _resolve_level(level: str) -> int:
    resolved = logging.getLevelNamesMapping().get(level.upper())
    if resolved is None:
        return logging.INFO
    return resolved
