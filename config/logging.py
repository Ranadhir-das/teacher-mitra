"""Minimal structured events: do not interpolate possibly sensitive messages."""
import json
import logging
from datetime import datetime, timezone


class SafeJSONFormatter(logging.Formatter):
    def format(self, record):
        event = {"timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname, "logger": record.name,
            "event": "application_error" if record.levelno >= logging.ERROR else "application_event"}
        if getattr(record, "status_code", None) is not None:
            event["status"] = record.status_code
        if record.exc_info and record.exc_info[0]:
            event["exception_type"] = record.exc_info[0].__name__
        return json.dumps(event)
