"""Application configuration."""

import logging
import math
import re
from enum import StrEnum
from pathlib import Path

from pydantic import SecretStr, ValidationInfo, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from financial_analyst_agent.domain.errors import ConfigurationError

_USER_AGENT_EMAIL_PATTERN = re.compile(
    r"^(.+?)\s+\(([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\)\s*$"
)


_LOGGER = logging.getLogger("financial_analyst_agent")
_DEPRECATED_APP_MODES = {"fixture": "recorded"}


class AppMode(StrEnum):
    """Which runtime `APP_MODE` selects: the recorded runtime or the live runtime."""

    LIVE = "live"
    RECORDED = "recorded"

    @classmethod
    def _missing_(cls, value: object) -> "AppMode | None":
        if not isinstance(value, str):
            return None
        normalized = value.strip().casefold()
        replacement = _DEPRECATED_APP_MODES.get(normalized)
        if replacement is not None:
            _LOGGER.warning(
                "APP_MODE=%s is deprecated; use APP_MODE=%s", normalized, replacement
            )
            normalized = replacement
        for member in cls:
            if member.value == normalized:
                return member
        return None


def _reject_non_finite(value: float, field_name: str) -> float:
    if math.isnan(value) or math.isinf(value):
        raise ValueError(f"{field_name} must be a finite number")
    return value


# SEC's fair-access limit is 10 requests a second for everything on one address.
# One limiter paces the whole process; 8 leaves room for anything else on the
# address (a snapshot build, a second process).
SEC_MAX_REQUESTS_PER_SECOND = 8.0


class Settings(BaseSettings):
    """Typed settings loaded from environment variables."""

    sec_user_agent: str = ""
    sec_base_url: str = "https://data.sec.gov"
    sec_max_requests_per_second: float = SEC_MAX_REQUESTS_PER_SECOND
    # Per connect or read: a hung SEC must not hold a three-company turn for 90 s.
    sec_timeout_seconds: float = 10.0
    # Wall clock for one SEC request, body included: a server that drips a byte
    # at a time never trips a per-read timeout.
    sec_request_deadline_seconds: float = 30.0
    # Decompressed: the largest real document (a BDC's 10-Q) is about 25 MB.
    sec_max_response_bytes: int = 64 * 1024 * 1024
    # SEC time one turn may spend; past it, the companies not yet read show
    # "Source unavailable" and the turn answers with the rest.
    sec_turn_budget_seconds: float = 90.0
    # How long every SEC request waits after SEC flags this app as an
    # undeclared automated tool (its 403 page asks for about ten minutes).
    sec_block_pause_seconds: float = 600.0
    sec_cache_dir: Path | None = None
    # How often the live runtime reads SEC's latest 10-Q and 10-K filings, so a
    # company's cached data lasts until it files again (ADR 0013); 0 turns it off.
    sec_filing_watch_seconds: float = 300.0
    # With the filing watch on, the largest companies' SEC data is fetched in the
    # background before anyone asks (ADR 0014), this many of them; 0 turns it off.
    sec_warm_companies: int = 250
    # The warm-up's share of SEC requests; it also waits while visitors' requests queue.
    sec_warm_requests_per_second: float = 2.0
    # The SEC disk cache is trimmed, oldest files first, past this size.
    sec_cache_max_bytes: int = 1024 * 1024 * 1024
    fmp_api_key: str = ""
    fmp_base_url: str = "https://financialmodelingprep.com"
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    openai_api_key: str = ""
    openai_model: str = "gpt-5.6-terra"
    openai_base_url: str = ""
    app_mode: AppMode = AppMode.LIVE
    public_demo: bool = False
    demo_live_sec: bool = False
    allow_public_openai: bool = False
    allow_public_tavily: bool = False
    api_proxy_token: SecretStr = SecretStr("")
    thread_ttl_seconds: int = 7200
    max_turns_per_thread: int = 25
    # A cold top-25 ranking reads about 50 SEC documents (a bank's paged
    # history, more); this fits two. Cached documents cost nothing.
    max_live_sec_requests_per_thread: int = 150
    max_concurrent_turns: int = 4
    # A turn still running after this ends with an error and frees its thread
    # and slot; above the SEC budget so a slow but working turn can finish.
    turn_timeout_seconds: float = 150.0
    # Per visitor (client IP), per rolling hour: threads cost nothing to open,
    # so the per-thread budgets alone do not bound what one visitor can spend.
    client_threads_per_hour: int = 30
    client_turns_per_hour: int = 120
    snapshot_stale_after_days: int = 30

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("sec_user_agent")
    @classmethod
    def validate_user_agent(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            return stripped
        match = _USER_AGENT_EMAIL_PATTERN.match(stripped)
        if match is None:
            raise ValueError(
                "SEC_USER_AGENT must include a descriptive application name and "
                "contact email, e.g. 'FinancialAnalystAgent (you@example.com)'"
            )
        if not match.group(1).strip():
            raise ValueError("SEC_USER_AGENT application name must be nonempty")
        return stripped

    @field_validator("sec_max_requests_per_second")
    @classmethod
    def validate_max_requests_per_second(cls, value: float) -> float:
        value = _reject_non_finite(value, "SEC_MAX_REQUESTS_PER_SECOND")
        if value <= 0 or value > SEC_MAX_REQUESTS_PER_SECOND:
            raise ValueError(
                "SEC_MAX_REQUESTS_PER_SECOND must be greater than 0 and at most "
                f"{SEC_MAX_REQUESTS_PER_SECOND:g}"
            )
        return value

    @field_validator(
        "sec_timeout_seconds",
        "sec_request_deadline_seconds",
        "sec_turn_budget_seconds",
        "turn_timeout_seconds",
    )
    @classmethod
    def validate_positive_seconds(cls, value: float, info: ValidationInfo) -> float:
        name = str(info.field_name).upper()
        value = _reject_non_finite(value, name)
        if value <= 0:
            raise ValueError(f"{name} must be greater than 0")
        return value

    @field_validator("sec_block_pause_seconds")
    @classmethod
    def validate_block_pause_seconds(cls, value: float) -> float:
        value = _reject_non_finite(value, "SEC_BLOCK_PAUSE_SECONDS")
        if value < 0:
            raise ValueError("SEC_BLOCK_PAUSE_SECONDS must not be negative")
        return value

    @field_validator("sec_warm_companies")
    @classmethod
    def validate_warm_companies(cls, value: int) -> int:
        if value < 0:
            raise ValueError("SEC_WARM_COMPANIES must not be negative (0 turns it off)")
        return value

    @field_validator("sec_warm_requests_per_second")
    @classmethod
    def validate_warm_rate(cls, value: float) -> float:
        value = _reject_non_finite(value, "SEC_WARM_REQUESTS_PER_SECOND")
        if value <= 0 or value > SEC_MAX_REQUESTS_PER_SECOND:
            raise ValueError(
                "SEC_WARM_REQUESTS_PER_SECOND must be greater than 0 and at most "
                f"{SEC_MAX_REQUESTS_PER_SECOND:g}"
            )
        return value

    @field_validator("sec_filing_watch_seconds")
    @classmethod
    def validate_filing_watch_seconds(cls, value: float) -> float:
        value = _reject_non_finite(value, "SEC_FILING_WATCH_SECONDS")
        if value < 0:
            raise ValueError("SEC_FILING_WATCH_SECONDS must not be negative (0 turns it off)")
        return value

    @field_validator("sec_max_response_bytes", "sec_cache_max_bytes")
    @classmethod
    def validate_byte_limit(cls, value: int, info: ValidationInfo) -> int:
        if value < 1024 * 1024:
            raise ValueError(f"{str(info.field_name).upper()} must be at least 1 MiB")
        return value

    @field_validator("max_concurrent_turns")
    @classmethod
    def validate_max_concurrent_turns(cls, value: int) -> int:
        if value < 1:
            raise ValueError("MAX_CONCURRENT_TURNS must be at least 1")
        return value

    @field_validator("fmp_base_url")
    @classmethod
    def validate_fmp_base_url(cls, value: str) -> str:
        stripped = value.strip().rstrip("/")
        if not stripped:
            raise ValueError("FMP_BASE_URL must be nonempty")
        return stripped

    @field_validator("tavily_base_url")
    @classmethod
    def validate_tavily_base_url(cls, value: str) -> str:
        stripped = value.strip().rstrip("/")
        if not stripped:
            raise ValueError("TAVILY_BASE_URL must be nonempty")
        return stripped

    def require_user_agent(self) -> str:
        if not self.sec_user_agent.strip():
            raise ConfigurationError(
                "SEC_USER_AGENT is required for live SEC access. "
                "Set SEC_USER_AGENT in the environment or .env file."
            )
        return self.sec_user_agent

    def require_fmp_api_key(self) -> str:
        key = self.fmp_api_key.strip()
        if not key:
            raise ConfigurationError(
                "FMP_API_KEY is required to rebuild the universe snapshot. "
                "Set FMP_API_KEY in the environment or .env file."
            )
        return key

    def require_tavily_api_key(self) -> str:
        key = self.tavily_api_key.strip()
        if not key:
            raise ConfigurationError(
                "TAVILY_API_KEY is required for live news search. "
                "Set TAVILY_API_KEY in the environment or .env file."
            )
        return key

    def require_openai_api_key(self) -> str:
        key = self.openai_api_key.strip()
        if not key:
            raise ConfigurationError(
                "OPENAI_API_KEY is required for the live planner. "
                "Set OPENAI_API_KEY in the environment or .env file."
            )
        return key

    def require_openai_model(self) -> str:
        model = self.openai_model.strip()
        if not model:
            raise ConfigurationError(
                "OPENAI_MODEL is required for the live planner. "
                "Set OPENAI_MODEL in the environment or .env file."
            )
        return model


def get_settings() -> Settings:
    return Settings()
