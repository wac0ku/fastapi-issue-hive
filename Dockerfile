# ---- builder: build the virtualenv, keep uv itself out of the runtime image ----
# Same base as the runtime stage on purpose: the .venv is copied across stages, so both
# sides must share a glibc/Python build. uv comes in as a pinned static binary.
FROM python:3.12-slim AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv

# UV_COMPILE_BYTECODE: ship .pyc files so the container starts faster.
# UV_LINK_MODE=copy:   the uv cache below is a mount, hardlinking out of it would fail.
# UV_PYTHON_DOWNLOADS=0: use the image's interpreter instead of fetching a managed one.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /srv/hive

# Dependencies only. The app is served from WORKDIR rather than installed, because
# prompts/ is not part of the wheel and app/services/claude.py resolves it relative to
# the directory above the package — see docs/09-code-review.md (P1-1).
# This layer is only invalidated when pyproject.toml or uv.lock change.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

# ---- runtime ----
FROM python:3.12-slim

WORKDIR /srv/hive

COPY --from=builder /srv/hive/.venv ./.venv
COPY app ./app
COPY prompts ./prompts
COPY README.md LICENSE ./

# Put the venv first on PATH instead of activating it. uvicorn additionally prepends its
# --app-dir (default ".") to sys.path, which is how `app.main:app` resolves from WORKDIR.
ENV PATH="/srv/hive/.venv/bin:$PATH"

EXPOSE 8000

# --host 0.0.0.0: reachable from outside the container (see docs/06-deployment.md)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
