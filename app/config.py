from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field is optional — without keys the hive
    runs in deterministic heuristic mode, which is what the test suite uses."""

    anthropic_api_key: str = ""
    github_token: str = ""
    hive_model: str = "claude-sonnet-5"
    max_issues_per_repo: int = 10
    # A repo scan analyses issues concurrently; this caps how many run at once so one
    # request cannot fan out into dozens of simultaneous Claude calls.
    max_concurrent_analyses: int = 5
    scan_timeout_seconds: float = 120.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def claude_enabled(self) -> bool:
        return bool(self.anthropic_api_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
