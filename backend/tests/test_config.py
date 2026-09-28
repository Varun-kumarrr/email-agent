from app.core.config import Settings


def test_allowed_origins_parsed_from_comma_separated_string(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "http://localhost:3000, https://app.example.com")
    settings = Settings(_env_file=None)
    assert settings.ALLOWED_ORIGINS == ["http://localhost:3000", "https://app.example.com"]


def test_secrets_are_masked_in_repr(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "super-secret-value")
    monkeypatch.setenv("LLM_API_KEY", "llm-secret-value")
    settings = Settings(_env_file=None)
    text = repr(settings)
    assert "super-secret-value" not in text
    assert "llm-secret-value" not in text
