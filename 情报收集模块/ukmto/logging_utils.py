import json
import logging
import os
import re


def redact(value: str) -> str:
    for name, secret in os.environ.items():
        if any(word in name.upper() for word in ("KEY", "SECRET", "PASSWORD", "TOKEN")):
            if len(secret) >= 6:
                value = value.replace(secret, "[REDACTED]")
    value = re.sub(r"(?i)(authorization|cookie|set-cookie)\s*[:=][^\r\n]*", r"\1=[REDACTED]", value)
    value = re.sub(r"(?i)Bearer\s+\S+", "Bearer [REDACTED]", value)
    value = re.sub(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b", "[REDACTED]", value)
    value = re.sub(r"\bsb_secret_[\w-]+\b", "[REDACTED]", value)
    value = re.sub(r"(https?://)[^\s/@]+:[^\s/@]+@", r"\1[REDACTED]@", value)
    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"level": record.levelname, "event": record.getMessage()}
        payload.update(getattr(record, "fields", {}))
        def scrub(value):
            if isinstance(value, str):
                return redact(value)
            if isinstance(value, dict):
                return {key: scrub(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [scrub(item) for item in value]
            return value
        return json.dumps(scrub(payload), ensure_ascii=False, default=str)


def configure_logging(verbose: bool = False) -> None:
    logger = logging.getLogger("ukmto")
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    logger.handlers[:] = [handler]
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    # Do not enable HTTP wire logs, even with --verbose.
    for name in ("httpx", "httpcore", "urllib3", "postgrest"):
        logging.getLogger(name).setLevel(logging.WARNING)


def log(event: str, *, level: int = logging.INFO, **fields) -> None:
    logging.getLogger("ukmto").log(level, event, extra={"fields": fields})


def error_fields(exc: Exception) -> dict[str, str]:
    return {"exception_type": type(exc).__name__, "message": redact(str(exc))[:1000]}
