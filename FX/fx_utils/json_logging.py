import json
import logging
import os
import re
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record):
        message=record.getMessage()
        message=re.sub(r"(?i)(authorization|password|token|api[_-]?key|cookie|private[_-]?key)\s*[:=]\s*[^\s,;]+",r"\1=<redacted>",message)
        payload = {"timestamp": datetime.now(timezone.utc).isoformat(), "level": record.levelname, "service": os.getenv("SERVICE_NAME","beyvra-backend"), "environment": os.getenv("DEPLOYMENT_ENV","unknown"), "event": getattr(record,"event",record.name), "logger": record.name, "message": message, "simulation": bool(getattr(record,"simulation",False))}
        for key in ("request_id", "correlation_id", "trace_id", "event_id", "legacy_prefix", "successor"):
            value = getattr(record, key, None)
            if value:
                payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = record.exc_info[0].__name__
        return json.dumps(payload, separators=(",", ":"), default=str)
