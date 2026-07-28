# 06 — Deployment

The hive is a stateless FastAPI app: no database, no filesystem writes, no sessions. Scale it like any stateless service — every deployment option below works with zero code changes.

## Bare uvicorn (single machine)

```bash
uv sync --locked --no-dev
uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
```

`--host 0.0.0.0` is required to accept connections from outside the machine — yes, the hive would triage that mistake as `connection_refused`.

## Docker

A production `Dockerfile` ships in the repo root:

```bash
docker build -t fastapi-issue-hive .
docker run -p 8000:8000 --env-file .env fastapi-issue-hive
```

Omit `--env-file .env` to run in pure heuristic mode.

## docker-compose

```yaml
services:
  hive:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY:-}
      - GITHUB_TOKEN=${GITHUB_TOKEN:-}
    restart: unless-stopped
```

## Behind nginx

```nginx
server {
    listen 443 ssl;
    server_name hive.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Start uvicorn with `--proxy-headers` so generated URLs respect the https scheme. To serve under a sub-path (e.g. `/hive`), add `--root-path /hive` and a matching `location /hive/` block — exactly as described by the hive's own `reverse_proxy` category.

## Free hosting

The heuristic mode's zero-dependency footprint fits free tiers comfortably (≈100 MB image, <100 MB RAM idle):

| Host | How |
|------|-----|
| **Render** | New Web Service → connect repo → it detects the Dockerfile. Free instances sleep after idle; first request wakes them. |
| **Fly.io** | `fly launch` (accepts the Dockerfile), `fly deploy`. |
| **Railway** | New project → Deploy from GitHub repo. |

Set `ANTHROPIC_API_KEY` / `GITHUB_TOKEN` as secrets in the host's dashboard — never in the image.

## Production checklist

- [ ] `GET /health` wired into your uptime monitoring (also reports active mode)
- [ ] API keys injected as secrets, not baked into images or committed
- [ ] Public deployments: add an auth layer (the app itself is unauthenticated) and rate-limit `/analyze/repo` (it triggers outbound GitHub API calls)
- [ ] TLS terminated at the proxy, `--proxy-headers` enabled
- [ ] CI green on the commit you deploy (`pytest` needs no keys — run it anywhere)
