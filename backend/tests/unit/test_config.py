import pytest

from app.config import Settings, get_settings
from app.domain.value_objects import Provider


def test_defaults_are_mock_first_and_zero_cost() -> None:
    settings = Settings()

    assert settings.use_mocks is True
    assert settings.openrouter_enabled is False  # stays strictly $0
    assert settings.provider_order == (Provider.GEMINI, Provider.GROQ)
    assert settings.max_repair_attempts == 2
    assert settings.row_cap == 1000
    assert settings.statement_timeout_ms == 5000


def test_secrets_are_not_plaintext_by_default() -> None:
    settings = Settings()
    # SecretStr keeps keys out of reprs/logs (LLM02/LLM07).
    assert settings.gemini_api_key.get_secret_value() == ""
    assert "SecretStr" in repr(settings.gemini_api_key) or "**" in repr(settings.gemini_api_key)


def test_env_overrides_are_read(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATACHAT_USE_MOCKS", "false")
    monkeypatch.setenv("DATACHAT_MAX_REPAIR_ATTEMPTS", "5")

    settings = Settings()

    assert settings.use_mocks is False
    assert settings.max_repair_attempts == 5


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()


# --- env parsing of list-valued settings -----------------------------------
# A deploy died on `DATACHAT_CORS_ORIGINS=https://app.vercel.app` because
# pydantic-settings JSON-decodes collection fields at the source. Nobody types a
# JSON array into a PaaS env box, so both forms must work.


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://a.vercel.app", ("https://a.vercel.app",)),
        (
            "https://a.vercel.app,https://b.vercel.app",
            ("https://a.vercel.app", "https://b.vercel.app"),
        ),
        (
            " https://a.vercel.app , https://b.vercel.app ",
            ("https://a.vercel.app", "https://b.vercel.app"),
        ),
        ('["https://a.vercel.app"]', ("https://a.vercel.app",)),
        ("https://a.vercel.app,", ("https://a.vercel.app",)),
    ],
)
def test_cors_origins_accepts_plain_comma_separated_and_json(
    monkeypatch: pytest.MonkeyPatch, raw: str, expected: tuple[str, ...]
) -> None:
    monkeypatch.setenv("DATACHAT_CORS_ORIGINS", raw)
    assert Settings().cors_origins == expected


def test_provider_order_accepts_comma_separated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATACHAT_PROVIDER_ORDER", "groq,gemini")
    assert [p.value for p in Settings().provider_order] == ["groq", "gemini"]


def test_list_settings_keep_their_defaults_when_unset() -> None:
    settings = Settings()
    assert settings.cors_origins == ("http://localhost:3000",)
    assert [p.value for p in settings.provider_order] == ["gemini", "groq"]
