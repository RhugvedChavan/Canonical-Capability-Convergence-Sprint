from __future__ import annotations
import json
import logging
import sys
from datetime import datetime, timezone

_RESERVED = set(logging.LogRecord(None, None, "", 0, "", (), None).__dict__.keys())


class JsonFormatter(logging.Formatter):
    def __init__(self, *args, service_context: dict | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        # Baked into every line so multi-service log aggregation can filter
        # by service/environment without parsing free-text messages.
        self._service_context = service_context or {}

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            **self._service_context,
        }
        # Include any `extra={...}` fields the caller attached.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(
    level: str = "INFO",
    fmt: str = "json",
    service_name: str | None = None,
    environment: str | None = None,
) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())

    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if fmt == "json":
        service_context = {}
        if service_name:
            service_context["service"] = service_name
        if environment:
            service_context["environment"] = environment
        handler.setFormatter(JsonFormatter(service_context=service_context))
    else:
        prefix = f"{service_name} | " if service_name else ""
        handler.setFormatter(
            logging.Formatter(f"%(asctime)s | %(levelname)-8s | {prefix}%(name)s | %(message)s")
        )
    root.addHandler(handler)
