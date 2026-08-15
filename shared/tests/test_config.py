"""Config env var wiring (review #15): must read unprefixed names matching
.env.example / docker-compose's env_file / Cloud Run --set-secrets, not
SECONDUNIT_*-prefixed ones."""
from shared.config import Config


def test_config_reads_unprefixed_env_vars(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-gemini-key")
    monkeypatch.setenv("GRAFANA_URL", "https://test.grafana.net")
    monkeypatch.setenv("HANDS_SERVICE_URL", "http://hands:9999")
    monkeypatch.setenv("SCHEDULER_TOKEN", "test-token")

    config = Config()

    assert config.gemini_api_key == "test-gemini-key"
    assert config.grafana_url == "https://test.grafana.net"
    assert config.hands_service_url == "http://hands:9999"
    assert config.scheduler_token == "test-token"


def test_config_ignores_prefixed_env_vars(monkeypatch):
    """A SECONDUNIT_-prefixed var must NOT be picked up — that was
    exactly the bug: env_prefix silently broke every documented var."""
    monkeypatch.setenv("SECONDUNIT_GEMINI_API_KEY", "should-not-be-read")
    config = Config()
    assert config.gemini_api_key == ""


def test_config_defaults_when_unset(monkeypatch):
    monkeypatch.delenv("HANDS_SERVICE_URL", raising=False)
    config = Config()
    assert config.hands_service_url == "http://hands:8080"
    assert config.scheduler_token == ""
    assert config.poll_cooldown_seconds == 300
