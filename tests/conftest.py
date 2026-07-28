"""Test isolation.

The suite's whole premise is that it runs offline with no keys. Settings are read from
the process environment, though, so a developer (or CI runner) with ANTHROPIC_API_KEY set
would have had the tests make real, billable API calls, and a stray GITHUB_TOKEN silently
changed which headers the client sent. Both are cleared here for every test.
"""

from collections.abc import Iterator

import pytest

from app.config import get_settings
from app.services import claude, github

# Every field pydantic-settings would pick up from the environment.
_SETTINGS_ENV = (
    "ANTHROPIC_API_KEY",
    "GITHUB_TOKEN",
    "HIVE_MODEL",
    "MAX_ISSUES_PER_REPO",
    "MAX_CONCURRENT_ANALYSES",
    "SCAN_TIMEOUT_SECONDS",
    "ALLOWED_ORIGINS",
)


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Run every test against a pristine, keyless configuration."""
    for name in _SETTINGS_ENV:
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    # Settings are cached, and the cached instance may predate the cleanup above.
    get_settings.cache_clear()
    claude._client.cache_clear()
    github._client.cache_clear()
    yield
    get_settings.cache_clear()
