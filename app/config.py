from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. Every field is optional — without keys the hive
    runs in deterministic heuristic mode, which is what the test suite uses."""

    # SecretStr, not str: these end up in reprs, tracebacks and log records, and
    # SecretStr masks them there. Read the value with .get_secret_value().
    anthropic_api_key: SecretStr = SecretStr("")
    github_token: SecretStr = SecretStr("")
    hive_model: str = "claude-sonnet-5"
    max_issues_per_repo: int = 10
    # A repo scan analyses issues concurrently; this caps how many run at once so one
    # request cannot fan out into dozens of simultaneous Claude calls.
    max_concurrent_analyses: int = 5
    scan_timeout_seconds: float = 120.0
    # Origins allowed to call the API from a browser. Empty means no CORS headers at
    # all, which is the safe default for a service with no authentication.
    allowed_origins: tuple[str, ...] = ()

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def claude_enabled(self) -> bool:
        return bool(self.anthropic_api_key.get_secret_value())

    @property
    def github_authenticated(self) -> bool:
        return bool(self.github_token.get_secret_value())


@lru_cache
def get_settings() -> Settings:
    return Settings()
