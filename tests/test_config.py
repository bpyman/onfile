"""Settings load live credentials from the environment / .env file."""

import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ConfigurationError


def test_settings_loads_fmp_api_key_and_sec_user_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "test-fmp-key")
    monkeypatch.setenv("SEC_USER_AGENT", "FinancialAnalystAgent (dev@example.com)")
    monkeypatch.setenv("FMP_BASE_URL", "https://fmp.example")

    settings = Settings()

    assert settings.require_fmp_api_key() == "test-fmp-key"
    assert settings.require_user_agent() == "FinancialAnalystAgent (dev@example.com)"
    assert settings.fmp_base_url == "https://fmp.example"


def test_settings_require_fmp_api_key_points_at_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FMP_API_KEY", "")

    with pytest.raises(ConfigurationError, match=r"FMP_API_KEY.*\.env"):
        Settings().require_fmp_api_key()


def test_settings_require_tavily_api_key_points_at_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "")

    with pytest.raises(ConfigurationError, match=r"TAVILY_API_KEY.*\.env"):
        Settings().require_tavily_api_key()


def test_settings_require_openai_api_key_points_at_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")

    with pytest.raises(ConfigurationError, match=r"OPENAI_API_KEY.*\.env"):
        Settings().require_openai_api_key()


def test_sec_requests_default_to_eight_a_second_and_never_more(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SEC_MAX_REQUESTS_PER_SECOND", raising=False)
    assert Settings(_env_file=None).sec_max_requests_per_second == 8

    monkeypatch.setenv("SEC_MAX_REQUESTS_PER_SECOND", "8.5")
    with pytest.raises(ValueError, match="at most 8"):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("method", "message"),
    [
        (
            "require_user_agent",
            "SEC_USER_AGENT is required for live SEC access. "
            "Set SEC_USER_AGENT in the environment or .env file.",
        ),
        (
            "require_fmp_api_key",
            "FMP_API_KEY is required to rebuild the universe snapshot. "
            "Set FMP_API_KEY in the environment or .env file.",
        ),
        (
            "require_tavily_api_key",
            "TAVILY_API_KEY is required for live news search. "
            "Set TAVILY_API_KEY in the environment or .env file.",
        ),
        (
            "require_openai_api_key",
            "OPENAI_API_KEY is required for the live planner. "
            "Set OPENAI_API_KEY in the environment or .env file.",
        ),
        (
            "require_openai_model",
            "OPENAI_MODEL is required for the live planner. "
            "Set OPENAI_MODEL in the environment or .env file.",
        ),
    ],
)
def test_a_missing_setting_is_named_with_what_it_is_for(method: str, message: str) -> None:
    blank = Settings(
        _env_file=None,
        sec_user_agent="",
        fmp_api_key=" ",
        tavily_api_key="",
        openai_api_key="\t",
        openai_model="",
    )
    with pytest.raises(ConfigurationError) as raised:
        getattr(blank, method)()
    assert str(raised.value) == message


def test_a_required_setting_is_returned_without_its_surrounding_spaces() -> None:
    settings = Settings(
        _env_file=None,
        sec_user_agent=" FinancialAnalystAgent (dev@example.com) ",
        fmp_api_key=" fmp ",
        tavily_api_key=" tavily ",
        openai_api_key=" openai ",
        openai_model=" model ",
    )
    assert settings.require_user_agent() == "FinancialAnalystAgent (dev@example.com)"
    assert settings.require_fmp_api_key() == "fmp"
    assert settings.require_tavily_api_key() == "tavily"
    assert settings.require_openai_api_key() == "openai"
    assert settings.require_openai_model() == "model"


@pytest.mark.parametrize("field", ["fmp_base_url", "tavily_base_url"])
def test_a_provider_base_url_loses_its_trailing_slash_and_may_not_be_blank(field: str) -> None:
    trimmed = Settings(_env_file=None, **{field: " https://api.example/ "})
    assert getattr(trimmed, field) == "https://api.example"

    with pytest.raises(ValueError, match=f"{field.upper()} must be nonempty"):
        Settings(_env_file=None, **{field: " / "})
