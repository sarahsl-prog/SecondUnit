from pydantic_settings import BaseSettings

class Config(BaseSettings):
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-exp"
    grafana_url: str = ""
    grafana_api_key: str = ""
    gcp_project_id: str = ""
    gcp_zone: str = "us-central1-a"
    hands_service_url: str = "http://hands:8080"
    slack_webhook_url: str = ""
    scheduler_token: str = ""
    poll_cooldown_seconds: int = 300
    budget_state_path: str = "/tmp/secondunit-budget-state.json"

    class Config:
        env_prefix = "SECONDUNIT_"  # Optional prefix
        env_file = ".env"
