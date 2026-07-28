# ---- builder: build the virtualenv, keep uv itself out of the runtime image ----
# Same base as the runtime stage on purpose: the .venv is copied across stages, so both
# sides must share a glibc/Python build. uv comes in as a pinned static binary.
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de AS builder

COPY --from=ghcr.io/astral-sh/uv:0.8.17 /uv /bin/uv

# UV_COMPILE_BYTECODE: ship .pyc files so the container starts faster.
# UV_LINK_MODE=copy:   the uv cache below is a mount, hardlinking out of it would fail.
# UV_PYTHON_DOWNLOADS=0: use the image's interpreter instead of fetching a managed one.
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /srv/hive

# Dependencies first, without the project: this layer is only invalidated when
# pyproject.toml or uv.lock change, not on every source edit.
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    uv sync --locked --no-dev --no-install-project

# Then the project itself, installed properly rather than served from the source tree —
# the prompt templates are package data now, so nothing depends on the layout any more.
COPY pyproject.toml uv.lock README.md ./
COPY app ./app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---- runtime ----
FROM python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de

# Run as an unprivileged account: nothing here needs root, and a container escape should
# not start from uid 0.
RUN useradd --system --create-home --uid 10001 hive

WORKDIR /srv/hive

COPY --from=builder --chown=hive:hive /srv/hive/.venv ./.venv
COPY --chown=hive:hive LICENSE ./

# Put the venv first on PATH instead of activating it.
ENV PATH="/srv/hive/.venv/bin:$PATH"

USER hive

EXPOSE 8000

# Uses the app's own liveness endpoint, so an unhealthy container is visible to the
# orchestrator rather than only in the logs.
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health').read()"

# --host 0.0.0.0: reachable from outside the container (see docs/06-deployment.md)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
