"""FastAPI Issue Hive — hive-mind analysis of FastAPI connectivity issues."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Read from the installed distribution so pyproject.toml stays the single source of
    # truth; a hardcoded copy here silently drifts on the next release.
    __version__ = version("fastapi-issue-hive")
except PackageNotFoundError:  # pragma: no cover - only when running from an unbuilt tree
    __version__ = "0.0.0+unknown"
