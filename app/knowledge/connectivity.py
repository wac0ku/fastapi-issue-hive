"""Curated knowledge base of FastAPI connectivity failure modes.

Each category carries regex signals for triage plus root causes, fixes and
documentation links for diagnosis. This is what makes the hive useful with
zero API keys — Claude only *enhances* these answers, it is never required.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ConnectivityCategory:
    id: str
    name: str
    description: str
    signals: list[str] = field(default_factory=list)
    root_causes: list[str] = field(default_factory=list)
    fixes: list[str] = field(default_factory=list)
    doc_links: list[str] = field(default_factory=list)


CATEGORIES: list[ConnectivityCategory] = [
    ConnectivityCategory(
        id="cors",
        name="CORS / Cross-Origin",
        description="Browser blocks requests because CORS headers are missing or misconfigured.",
        signals=[
            r"\bcors\b", r"access-control-allow-origin", r"preflight",
            r"blocked by cors", r"cross[- ]origin", r"\boptions request\b",
        ],
        root_causes=[
            "CORSMiddleware not added, or added after other middleware that short-circuits the response",
            "allow_origins does not include the exact frontend origin (scheme + host + port must match)",
            "allow_origins=['*'] combined with allow_credentials=True — the spec forbids wildcard with credentials",
            "A reverse proxy (nginx/Traefik/Cloudflare) strips or duplicates CORS headers",
            "Custom request headers (Authorization, X-CSRF-Token) not whitelisted in allow_headers",
        ],
        fixes=[
            "app.add_middleware(CORSMiddleware, allow_origins=['https://your-frontend.example'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])",
            "List explicit origins instead of '*' when cookies/credentials are involved",
            "Handle CORS in exactly one layer — either FastAPI or the proxy, never both",
            "Check the browser DevTools network tab: a failing OPTIONS preflight pinpoints the missing header",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/tutorial/cors/",
            "https://developer.mozilla.org/en-US/docs/Web/HTTP/CORS",
        ],
    ),
    ConnectivityCategory(
        id="connection_refused",
        name="Connection Refused / Binding",
        description="Clients cannot reach the server at all — wrong bind address, port conflict, or firewall.",
        signals=[
            r"connection refused", r"err_connection_refused", r"address already in use",
            r"port already in use", r"can'?t connect", r"cannot connect", r"\b127\.0\.0\.1\b",
            r"\b0\.0\.0\.0\b", r"connection reset",
        ],
        root_causes=[
            "uvicorn binds to 127.0.0.1 by default — unreachable from other machines or containers",
            "Another process already occupies the port (address already in use)",
            "Firewall or cloud security group blocks the port",
            "Client uses http:// against an https:// only endpoint or vice versa",
        ],
        fixes=[
            "Run uvicorn app.main:app --host 0.0.0.0 --port 8000 to accept external connections",
            "Find the conflicting process with lsof -i :8000 (or netstat on Windows) and free the port",
            "Open the port in the firewall / security group of the host",
            "Verify with curl -v http://localhost:8000/health from the server itself first, then from outside",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/deployment/manually/",
            "https://www.uvicorn.org/settings/",
        ],
    ),
    ConnectivityCategory(
        id="reverse_proxy",
        name="Reverse Proxy (nginx / Traefik / Cloudflare)",
        description="502/504 errors, wrong scheme/host in URLs, or broken docs behind a proxy.",
        signals=[
            r"\bnginx\b", r"\btraefik\b", r"reverse proxy", r"\b502\b", r"\b504\b",
            r"bad gateway", r"gateway time-?out", r"root_path", r"x-forwarded",
            r"\bcloudflare\b", r"behind (a )?proxy",
        ],
        root_causes=[
            "Proxy forwards to the wrong upstream host/port (502 Bad Gateway)",
            "Upstream response exceeds the proxy read timeout (504 Gateway Timeout)",
            "X-Forwarded-Proto / X-Forwarded-For headers not passed, so FastAPI generates http:// URLs behind https",
            "App served under a sub-path without --root-path, breaking /docs and generated URLs",
        ],
        fixes=[
            "In nginx: proxy_pass http://127.0.0.1:8000; proxy_set_header Host $host; proxy_set_header X-Forwarded-Proto $scheme;",
            "Raise proxy_read_timeout for long-running endpoints, or make them async/streamed",
            "Start uvicorn with --proxy-headers --forwarded-allow-ips='*' (trusted networks only)",
            "Serve under a sub-path with uvicorn --root-path /api and matching proxy location block",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/deployment/behind-a-proxy/",
            "https://www.uvicorn.org/deployment/#running-behind-nginx",
        ],
    ),
    ConnectivityCategory(
        id="timeout",
        name="Timeouts / Hanging Requests",
        description="Requests hang, time out, or the server stops responding under load.",
        signals=[
            r"time[d]? ?out", r"\btimeout\b", r"hang(s|ing)?", r"stuck", r"keep-?alive",
            r"slow response", r"no response", r"never returns",
        ],
        root_causes=[
            "Blocking I/O (requests, time.sleep, sync DB drivers) inside async def blocks the event loop",
            "Database connection pool exhausted — requests queue waiting for a connection",
            "Client or proxy timeout shorter than the endpoint's real processing time",
            "Deadlock: an endpoint awaits another endpoint of the same single-worker app",
        ],
        fixes=[
            "Use sync def for blocking code (FastAPI runs it in a threadpool) or switch to async libraries (httpx, asyncpg)",
            "Never call time.sleep in async code — use await asyncio.sleep",
            "Size DB pools to worker count and always release connections (use dependencies with yield)",
            "Move slow work to BackgroundTasks or a task queue and return 202 immediately",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/async/",
            "https://fastapi.tiangolo.com/tutorial/background-tasks/",
        ],
    ),
    ConnectivityCategory(
        id="websocket",
        name="WebSocket Connectivity",
        description="WebSocket connections fail to establish, drop unexpectedly, or close with 1006.",
        signals=[
            r"websocket", r"\bws://", r"\bwss://", r"\b1006\b", r"connection closed",
            r"handshake", r"socket\.io",
        ],
        root_causes=[
            "Proxy not configured for the WebSocket Upgrade handshake",
            "ws:// used from an https page (mixed content) instead of wss://",
            "Idle connections killed by proxy/load-balancer timeouts (close code 1006)",
            "Endpoint never calls await websocket.accept() before send/receive",
        ],
        fixes=[
            "nginx: proxy_http_version 1.1; proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection 'upgrade';",
            "Always use wss:// when the page is served over https",
            "Send application-level ping/pong keepalives more often than the proxy idle timeout",
            "Call await websocket.accept() first and handle WebSocketDisconnect explicitly",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/advanced/websockets/",
            "https://www.nginx.com/blog/websocket-nginx/",
        ],
    ),
    ConnectivityCategory(
        id="ssl_https",
        name="SSL / HTTPS",
        description="Certificate errors, mixed content, or redirect loops on HTTPS deployments.",
        signals=[
            r"\bssl\b", r"\btls\b", r"certificate", r"certificate_verify_failed",
            r"mixed content", r"\bhttps\b", r"redirect loop", r"err_cert",
        ],
        root_causes=[
            "Self-signed or expired certificate rejected by clients",
            "HTTPS terminated at the proxy but the app redirects to http:// (missing X-Forwarded-Proto)",
            "Frontend on https calls the API on plain http (mixed content, silently blocked)",
            "Redirect loop: proxy and app both try to force HTTPS",
        ],
        fixes=[
            "Terminate TLS at the proxy with a Let's Encrypt certificate (certbot) and forward plain HTTP internally",
            "Pass X-Forwarded-Proto and run uvicorn with --proxy-headers so url_for generates https URLs",
            "Serve the API over HTTPS whenever the frontend is on HTTPS",
            "Enforce HTTPS in exactly one layer (proxy redirect or HTTPSRedirectMiddleware, not both)",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/deployment/https/",
        ],
    ),
    ConnectivityCategory(
        id="docker_networking",
        name="Docker / Container Networking",
        description="Services cannot reach each other inside Docker/Kubernetes, or the app is unreachable from the host.",
        signals=[
            r"\bdocker\b", r"docker-?compose", r"\bkubernetes\b", r"\bk8s\b",
            r"container", r"host\.docker\.internal", r"service name", r"getaddrinfo",
            r"name or service not known",
        ],
        root_causes=[
            "App binds to 127.0.0.1 inside the container — invisible to the host and other containers",
            "Container uses localhost to reach a sibling service instead of the compose service name",
            "Port not published (-p 8000:8000 / ports: in compose)",
            "Containers on different Docker networks cannot resolve each other",
        ],
        fixes=[
            "CMD [\"uvicorn\", \"app.main:app\", \"--host\", \"0.0.0.0\", \"--port\", \"8000\"] in the Dockerfile",
            "Use the compose service name as hostname (e.g. http://api:8000, postgres://db:5432)",
            "Publish the port in docker run -p or the compose ports section",
            "From a container to the host machine use host.docker.internal (add extra_hosts on Linux)",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/deployment/docker/",
            "https://docs.docker.com/network/",
        ],
    ),
    ConnectivityCategory(
        id="event_loop_blocking",
        name="Event Loop Blocking / Concurrency",
        description="The server handles only one request at a time or throughput collapses under load.",
        signals=[
            r"one request at a time", r"blocking", r"event loop", r"concurrent requests?",
            r"requests? queue", r"sequential", r"single worker", r"not parallel",
        ],
        root_causes=[
            "CPU-bound or sync-blocking code inside async def endpoints starves the event loop",
            "Single uvicorn worker serving CPU-heavy traffic",
            "Sync SQLAlchemy/requests calls awaited nowhere, blocking every other coroutine",
        ],
        fixes=[
            "Declare blocking endpoints with plain def — FastAPI executes them in a threadpool",
            "Offload CPU-bound work with run_in_executor or a worker queue (Celery, arq)",
            "Scale out: uvicorn --workers N (or gunicorn -k uvicorn.workers.UvicornWorker)",
            "Adopt async-native drivers (asyncpg, httpx.AsyncClient) end to end",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/async/",
            "https://fastapi.tiangolo.com/deployment/server-workers/",
        ],
    ),
    ConnectivityCategory(
        id="streaming",
        name="Streaming / SSE Buffering",
        description="StreamingResponse or Server-Sent Events arrive all at once instead of incrementally.",
        signals=[
            r"streamingresponse", r"server-?sent events", r"\bsse\b", r"chunked",
            r"buffer(ing|ed)?", r"stream(ing)? (not|doesn'?t) work", r"eventsource",
        ],
        root_causes=[
            "nginx buffers the upstream response by default, collapsing the stream",
            "Generator does synchronous blocking work between chunks",
            "Missing media_type='text/event-stream' and no-cache headers for SSE",
            "Client library waits for the full body instead of iterating chunks",
        ],
        fixes=[
            "Send the X-Accel-Buffering: no response header (or proxy_buffering off in nginx)",
            "Yield from an async generator and await between chunks",
            "For SSE set media_type='text/event-stream' and Cache-Control: no-cache",
            "Consume with httpx stream() / EventSource on the client instead of a plain GET",
        ],
        doc_links=[
            "https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse",
        ],
    ),
]
