"""Where a compiled surface's messages go once a `ui-mcp` tool handler produces them
(PHASE-6 SS4's own worked example calls this `sse.push(session_id, surface.messages)`).

`UISink` is a `Protocol`, not an ABC, deliberately: `src/mcp` may not import `fastapi`
(`tests/test_layer_boundary.py`), so the concrete SSE transport has to live in `src/api` and
be handed down as a plain object shaped like this -- structural typing means `src/mcp/ui`
never needs to import anything from `src/api` to describe what it needs from it.

`QueueUISink` is the one concrete implementation this layer *does* own: it needs nothing
`fastapi`-shaped, just `asyncio.Queue`, so `src/api`'s SSE route can `async for` the same
queue this module's tool handlers push into rather than the two layers needing a second
transport just to talk to each other.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol

from src.mcp.ui.messages import Message


class UISink(Protocol):
    async def push(self, messages: list[Message]) -> None: ...


class NullUISink:
    """The default when no session-scoped transport is wired up -- gates and unit tests that
    only care about *what* the compiler produced, not where it went.
    """

    def __init__(self) -> None:
        self.pushed: list[Message] = []

    async def push(self, messages: list[Message]) -> None:
        self.pushed.extend(messages)


class QueueUISink:
    """One session's worth of outbound A2UI traffic. `stream()` is what `GET
    /sessions/{id}/events` (src/api) iterates to write SSE frames.
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[Message] = asyncio.Queue()

    async def push(self, messages: list[Message]) -> None:
        for message in messages:
            await self._queue.put(message)

    async def stream(self) -> AsyncIterator[Message]:
        while True:
            yield await self._queue.get()
