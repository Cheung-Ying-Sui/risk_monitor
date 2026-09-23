import math
import os
from dataclasses import dataclass


class ConfigurationError(ValueError):
    pass


@dataclass(frozen=True)
class Settings:
    timeout: float = 30
    retries: int = 3  # Additional attempts after the initial request.
    max_incidents: int = 100
    request_interval: float = 1
    poll_interval_minutes: int = 10
    user_agent: str = "RiskMonitor/0.1 (UKMTO incident ingestion)"

    @classmethod
    def from_env(cls, max_incidents: int | None = None) -> "Settings":
        try:
            settings = cls(
                timeout=float(os.getenv("UKMTO_REQUEST_TIMEOUT_SECONDS", "30")),
                retries=int(os.getenv("UKMTO_REQUEST_RETRIES", "3")),
                max_incidents=(max_incidents if max_incidents is not None else
                               int(os.getenv("UKMTO_MAX_INCIDENTS_PER_RUN", "100"))),
                request_interval=float(os.getenv("UKMTO_REQUEST_INTERVAL_SECONDS", "1")),
                poll_interval_minutes=int(os.getenv("UKMTO_POLL_INTERVAL_MINUTES", "10")),
                user_agent=os.getenv("UKMTO_USER_AGENT", cls.user_agent),
            )
        except ValueError as exc:
            raise ConfigurationError("UKMTO numeric configuration is invalid") from exc
        if (not math.isfinite(settings.timeout) or not 0 < settings.timeout <= 300
                or not 0 <= settings.retries <= 5
                or not 1 <= settings.max_incidents <= 1000
                or not math.isfinite(settings.request_interval)
                or settings.request_interval < 1
                or settings.poll_interval_minutes < 1
                or not settings.user_agent.strip()
                or any(c in settings.user_agent for c in "\r\n")):
            raise ConfigurationError("UKMTO configuration is outside allowed bounds")
        return settings
