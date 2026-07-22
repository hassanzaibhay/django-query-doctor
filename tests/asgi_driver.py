"""Drive requests through Django's real ASGI handler.

``django.test.AsyncClient`` is not usable for testing this package's ASGI
behaviour. It calls ``get_response_async`` directly (``django/test/client.py``)
and so never enters ``ASGIHandler.__call__``, which is where Django opens the
per-request ``ThreadSensitiveContext`` (``django/core/handlers/asgi.py``).

That context decides which thread Django's thread-sensitive executor runs sync
work on, and therefore which ``connections["default"]`` object the ORM uses --
the exact variable that determines whether the middleware's ``execute_wrapper``
sees any queries. Testing ASGI capture through ``AsyncClient`` would exercise a
path that does not exist in production.
"""

from __future__ import annotations

import asyncio
from typing import Any

from django.core.handlers.asgi import ASGIHandler


def build_scope(path: str, method: str = "GET") -> dict[str, Any]:
    """Return a minimal, valid ASGI HTTP connection scope for ``path``."""
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }


async def asgi_get(path: str, handler: ASGIHandler | None = None) -> tuple[int, bytes]:
    """Send one GET through an ASGIHandler; return (status, body).

    The handler is built here when not supplied, because ``ASGIHandler.__init__``
    runs ``load_middleware()`` and so must happen inside whatever
    ``override_settings`` block the test is using. Concurrent callers share one
    handler, exactly as a real ASGI server does.
    """
    handler = ASGIHandler() if handler is None else handler
    messages: list[dict[str, Any]] = []
    finished = asyncio.Event()
    body_sent = False

    async def receive() -> dict[str, Any]:
        # One request message, then block until the response completes.
        # Returning http.request again trips Django's listen_for_disconnect
        # assertion; returning http.disconnect early aborts the request.
        nonlocal body_sent
        if not body_sent:
            body_sent = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await finished.wait()
        return {"type": "http.disconnect"}

    async def send(message: dict[str, Any]) -> None:
        messages.append(message)
        if message["type"] == "http.response.body" and not message.get("more_body"):
            finished.set()

    await handler(build_scope(path), receive, send)

    start = next(m for m in messages if m["type"] == "http.response.start")
    body = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
    return start["status"], body


def asgi_get_sync(path: str) -> tuple[int, bytes]:
    """Synchronous wrapper around :func:`asgi_get` for use in plain pytest tests."""
    return asyncio.run(asgi_get(path))


def asgi_get_concurrent_sync(paths: list[str]) -> list[tuple[int, bytes]]:
    """Send all ``paths`` concurrently through one shared ASGIHandler."""

    async def _run() -> list[tuple[int, bytes]]:
        handler = ASGIHandler()
        return list(await asyncio.gather(*(asgi_get(p, handler) for p in paths)))

    return asyncio.run(_run())
