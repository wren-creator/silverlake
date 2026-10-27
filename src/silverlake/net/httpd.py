"""A small HTTP/1.0 listener for the console: read one request, answer it, close. No keep alive, no chunking,
a capped body. It runs in the same event loop as the 5250 listener, so the store is only ever touched by one
thing at a time."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from ..system.profiles import ProfileStore
from .httpadmin import MAX_BODY, Request, Response, State, handle

log = logging.getLogger("silverlake.http")

HEAD_LIMIT = 16 * 1024
READ_TIMEOUT = 10.0
REASONS = {200: "OK", 302: "Found", 400: "Bad Request", 401: "Unauthorized", 404: "Not Found", 409: "Conflict",
           413: "Payload Too Large"}


class TooLarge(Exception):
    pass


async def _read_request(reader: asyncio.StreamReader) -> Request | None:
    head = await reader.readuntil(b"\r\n\r\n")
    if len(head) > HEAD_LIMIT:
        return None
    lines = head.decode("latin-1").split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) < 2:
        return None
    headers = {}
    for line in lines[1:]:
        name, sep, value = line.partition(":")
        if sep:
            headers[name.strip().lower()] = value.strip()
    try:
        length = int(headers.get("content-length", "0"))
    except ValueError:
        return None
    if length < 0 or length > MAX_BODY:
        raise TooLarge
    body = (await reader.readexactly(length)).decode("utf-8", "replace") if length else ""
    return Request(parts[0], parts[1], headers, body)


def _wire(resp: Response) -> bytes:
    body = resp.body.encode("utf-8")
    head = [f"HTTP/1.0 {resp.status} {REASONS.get(resp.status, 'OK')}"]
    head += [f"{k}: {v}" for k, v in resp.headers.items()]
    head += [f"Content-Length: {len(body)}", "Connection: close", "", ""]
    return "\r\n".join(head).encode("latin-1") + body


async def serve(host: str, port: int, store_of: Callable[[], ProfileStore], ssl_context=None,
                state: State | None = None) -> asyncio.Server:
    state = state or State()

    async def on_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            req = await asyncio.wait_for(_read_request(reader), READ_TIMEOUT)
            if req is None:
                resp = Response(400, {"Server": "IBM HTTP Server for i"}, "")
            else:
                resp = handle(req, store_of(), state)
            writer.write(_wire(resp))
            await writer.drain()
        except TooLarge:
            writer.write(_wire(Response(413, {"Server": "IBM HTTP Server for i"}, "")))
            await writer.drain()
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, ConnectionError):
            pass
        except Exception:
            log.exception("http request failed")
        finally:
            writer.close()

    return await asyncio.start_server(on_client, host, port, ssl=ssl_context)
