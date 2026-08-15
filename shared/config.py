from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-exp"
    grafana_url: str = ""
    grafana_api_key: str = ""
    gcp_project_id: str = ""
    gcp_zone: str = "us-central1-a"
    hands_service_url: str = "http://hands:8080"
    simulator_url: str = "http://simulator:8080"
    slack_webhook_url: str = ""
    scheduler_token: str = ""
    poll_cooldown_seconds: int = 300
    budget_state_path: str = "/tmp/secondunit-budget-state.json"
    hands_retry_backoff_seconds: float = 1.0
    enable_real_gcp_actions: bool = False
    dispatcher_fallback_path: str = "/tmp/secondunit-unnotified-incidents.jsonl"

    # No env_prefix: .env.example, docker-compose's env_file, and Cloud Run
    # --set-secrets all use unprefixed names (GEMINI_API_KEY, not
    # SECONDUNIT_GEMINI_API_KEY) — a prefix here would silently break every
    # documented config source (review #15).
    model_config = SettingsConfigDict(env_file=".env")
