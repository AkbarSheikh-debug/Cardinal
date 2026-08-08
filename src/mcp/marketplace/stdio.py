"""Standalone stdio transport for `marketplace-mcp` (PHASE-2 §3, §8 gate 2.1/2.7).

    python -m src.mcp.marketplace.stdio

Point MCP Inspector or Claude Desktop at this. It serves the exact same `Server` instance
`build_marketplace_server` builds for in-process use -- same tools, same handlers, same
catalogue seed -- which is what makes "in-process and stdio return byte-identical results"
(gate 2.7) true by construction rather than by two implementations happening to agree today.
"""

from __future__ import annotations

import anyio

from src.adapters.store import InMemoryListingStore
from src.mcp.marketplace.server import build_marketplace_server


async def _run() -> None:
    from mcp.server.stdio import stdio_server

    store = InMemoryListingStore.seeded()
    config = build_marketplace_server(store, audience="model")
    server = config["instance"]
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


def main() -> None:
    anyio.run(_run)


if __name__ == "__main__":
    main()
