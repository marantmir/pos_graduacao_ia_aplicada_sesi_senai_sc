"""Structured (JSON) logging setup, replacing ad-hoc print()/console.log.

No external dependency: a small custom formatter is enough to emit one JSON
object per line, which any log aggregator (Render, Railway, etc.) can parse.
"""
from __future__ import annotations

import json
import logging
import sys


LOGGER_NAME = "football_intelligence"


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if logger.handlers:
        return logger

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    return logger


def log_event(logger: logging.Logger, message: str, level: int = logging.INFO, **fields) -> None:
    logger.log(level, message, extra={"extra_fields": fields})
