"""Labelled issue texts for measuring triage quality.

The scoring formula cannot be changed responsibly without something to measure it
against — without this, any tweak to a signal or a threshold is a guess. Each entry is
an issue text plus the category it should be filed under, or None when the hive should
decline it.

Texts are paraphrased from the recurring problem shapes documented in
docs/research/niche-analysis.md, not copied from specific issue trackers.
"""

from typing import NamedTuple


class Sample(NamedTuple):
    title: str
    body: str
    expected: str | None  # category id, or None when triage should decline
    labels: tuple[str, ...] = ()


POSITIVES: tuple[Sample, ...] = (
    Sample(
        "CORS error: blocked by CORS policy when calling API from React",
        "Browser console shows no 'Access-Control-Allow-Origin' header is present on the "
        "response. The preflight OPTIONS request fails before my GET ever runs.",
        "cors",
    ),
    Sample(
        "Preflight request fails with 400 for cross-origin POST",
        "Sending a cross-origin POST with a custom Authorization header. The OPTIONS "
        "request comes back without the allow-headers entry.",
        "cors",
    ),
    Sample(
        "Cannot connect to the API from another machine",
        "uvicorn prints 'running on 127.0.0.1:8000'. curl from my laptop says "
        "ERR_CONNECTION_REFUSED, from the server itself it works.",
        "connection_refused",
    ),
    Sample(
        "address already in use on startup",
        "Starting the app fails: 'address already in use'. Nothing else should own that "
        "port. Restarting the machine helps for a while.",
        "connection_refused",
    ),
    Sample(
        "502 Bad Gateway from nginx in front of uvicorn",
        "nginx returns 502 for every request. Hitting uvicorn directly on the box works "
        "fine, and /docs is broken behind the reverse proxy.",
        "reverse_proxy",
    ),
    Sample(
        "Generated URLs use http behind our TLS-terminating proxy",
        "We run behind Traefik with TLS termination. FastAPI builds http:// links, and "
        "the x-forwarded headers do not seem to arrive. root_path is set.",
        "reverse_proxy",
    ),
    Sample(
        "Requests hang and eventually time out under concurrent load",
        "Endpoints declared async def call a sync database driver. Only one request is "
        "processed at a time, everything else times out.",
        "event_loop_blocking",
    ),
    Sample(
        "Server stops responding when one endpoint runs a long computation",
        "A CPU heavy handler declared with async def blocks the event loop, so every "
        "other request stalls until it finishes.",
        "event_loop_blocking",
    ),
    Sample(
        "WebSocket closes with code 1006 in production",
        "The wss:// handshake succeeds locally. Behind nginx the connection closed error "
        "appears after a few seconds.",
        "websocket",
    ),
    Sample(
        "Cannot reach the API container from another compose service",
        "My frontend container gets 'name or service not known' when calling "
        "http://localhost:8000. Both services run via docker-compose.",
        "docker_networking",
    ),
    Sample(
        "Mixed content error after moving behind HTTPS",
        "The page is served over https but the API calls go to http, so the browser "
        "blocks them. Certificate verify failed shows up in the server logs too.",
        "ssl_https",
    ),
    Sample(
        "Streamed response only arrives once the endpoint finishes",
        "Using StreamingResponse for server-sent events. Nothing reaches the client "
        "until the generator completes — it looks buffered.",
        "streaming",
    ),
    Sample(
        "Intermittent disconnects on the realtime endpoint",
        "Clients drop off the realtime feed every couple of minutes and reconnect.",
        "websocket",
        ("websocket", "bug"),
    ),
)

# Issues the hive should decline. These are the expensive mistakes: a false positive
# produces a confident, wrong diagnosis and, with a key configured, pays for it.
NEGATIVES: tuple[Sample, ...] = (
    Sample(
        "Add a dark mode toggle to the settings page",
        "Design wants a theme switch. The fade timeout should be around 300ms.",
        None,
    ),
    Sample(
        "Feature request: CSV export for the results table",
        "It would be nice to download the results as CSV from the UI.",
        None,
    ),
    Sample(
        "Typo in the tutorial, chapter three",
        "The word 'dependancy' is misspelled in the dependency injection section.",
        None,
    ),
    Sample(
        "Please publish wheels for Python 3.13",
        "The package has no 3.13 wheels yet, so installs fall back to building.",
        None,
    ),
    Sample(
        "response_model validation broke after the Pydantic v2 upgrade",
        "Validator errors on every response since upgrading. The model uses a custom "
        "field validator that no longer runs.",
        None,
    ),
    Sample(
        "OpenAPI schema generation is slow with 400 routes",
        "Startup takes eight seconds because the schema is rebuilt for every route.",
        None,
    ),
    Sample(
        "BackgroundTasks never execute under the test client",
        "The task function is never entered when running through the test client, "
        "although it works when the app runs normally.",
        None,
    ),
    Sample(
        "mypy cannot infer the type behind Depends()",
        "Type hints for dependency injected parameters are not resolved, so every "
        "handler needs an explicit annotation.",
        None,
    ),
    Sample(
        "Add a rate limit decorator to the docs",
        "Many users ask how to throttle endpoints; a documented recipe would help.",
        None,
    ),
    Sample(
        "Session cookie is not set after login",
        "The login handler returns 200 but no cookie ends up in the browser jar. "
        "Same-site attribute is default.",
        None,
    ),
)

ALL_SAMPLES: tuple[Sample, ...] = POSITIVES + NEGATIVES
