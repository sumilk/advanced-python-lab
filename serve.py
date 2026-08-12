"""A minimal ASGI app that serves the generated site/ directory.

The site is a single self-contained HTML file, so you can just open it — this
exists for the times you want it on a real HTTP origin (sharing it on your
LAN, testing with the file:// restrictions lifted, or auto-reloading while
you edit a lesson).

    uv run learn.py site                        # build it first
    uv run --with uvicorn uvicorn serve:app --reload --port 8000

There is no framework here on purpose: this is the raw ASGI protocol, which
is worth reading once. `scope` describes the request, `receive` pulls request
events, and `send` pushes response events.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"


def resolve(path: str) -> Path | None:
    """Map a URL path to a file inside SITE, refusing anything outside it."""
    relative = path.lstrip("/") or "index.html"
    candidate = (SITE / relative).resolve()
    if not candidate.is_relative_to(SITE.resolve()):
        return None                       # directory traversal attempt
    if candidate.is_dir():
        candidate = candidate / "index.html"
    return candidate if candidate.is_file() else None


async def app(scope, receive, send) -> None:
    if scope["type"] == "lifespan":
        while True:
            message = await receive()
            if message["type"] == "lifespan.startup":
                if not (SITE / "index.html").exists():
                    print("site/index.html is missing — run: uv run learn.py site")
                await send({"type": "lifespan.startup.complete"})
            elif message["type"] == "lifespan.shutdown":
                await send({"type": "lifespan.shutdown.complete"})
                return

    if scope["type"] != "http":
        return

    if scope["method"] not in {"GET", "HEAD"}:
        await respond(send, 405, b"method not allowed", "text/plain")
        return

    target = resolve(scope["path"])
    if target is None:
        await respond(send, 404, b"not found", "text/plain")
        return

    media_type, _ = mimetypes.guess_type(target.name)
    body = target.read_bytes() if scope["method"] == "GET" else b""
    await respond(send, 200, body, media_type or "application/octet-stream",
                  length=target.stat().st_size)


async def respond(send, status: int, body: bytes, media_type: str,
                  length: int | None = None) -> None:
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", f"{media_type}; charset=utf-8".encode()),
            (b"content-length", str(length if length is not None else len(body)).encode()),
            (b"cache-control", b"no-store"),
        ],
    })
    await send({"type": "http.response.body", "body": body})
