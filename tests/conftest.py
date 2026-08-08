"""Shared fixtures.

The catalogue is generated once per session. It is deterministic and every model in it is
frozen or written-once, so rebuilding it per test would cost seconds and buy nothing.
"""

from __future__ import annotations

import asyncio
import os
import sys
from collections.abc import Iterator
from typing import Any

import pytest

from src.adapters.catalogue.generator import generate_catalogue
from src.adapters.db.session import ENV_DATABASE_URL
from src.adapters.registry import registered_adapters
from src.adapters.store import InMemoryListingStore
from src.domain.listing import Listing


def pytest_asyncio_loop_factories(config: object, item: object) -> dict[str, object] | None:
    """psycopg's async mode rejects Windows' default ProactorEventLoop.

    Uses pytest-asyncio's hook rather than overriding the `event_loop_policy` fixture --
    that override is deprecated, and `asyncio`'s policy API is itself slated for removal.
    """
    if sys.platform == "win32":
        return {"selector": asyncio.SelectorEventLoop}
    return None


@pytest.fixture(scope="session")
def catalogue() -> tuple[Listing, ...]:
    return generate_catalogue()


@pytest.fixture(scope="session")
def store(catalogue: tuple[Listing, ...]) -> InMemoryListingStore:
    return InMemoryListingStore(catalogue)


def _adapter_ids() -> list[str]:
    return [adapter.name for adapter in registered_adapters(InMemoryListingStore(()))]


@pytest.fixture(params=_adapter_ids())
def adapter(request: pytest.FixtureRequest, store: InMemoryListingStore):  # type: ignore[no-untyped-def]
    """Every registered adapter, one at a time.

    Parametrised over the registry rather than a hardcoded list, so a new marketplace is
    covered by the contract suite the moment it is registered (CONSTITUTION II.6).
    """
    from src.adapters.registry import adapter_by_name

    return adapter_by_name(store, request.param)


async def call_mcp_tool(server_instance: Any, name: str, arguments: dict[str, Any]) -> Any:
    """Invoke one tool through the real MCP `Server.request_handlers`, not a shortcut.

    Used by every `tests/unit/test_mcp_*` module (PHASE-2) so a test proves the same call
    path gate 2.6 relies on -- the SDK's own `CallToolRequest` handler -- actually works,
    not just that our handler function does when called directly in Python.
    """
    from mcp import types as mcp_types

    handler = server_instance.request_handlers[mcp_types.CallToolRequest]
    request = mcp_types.CallToolRequest(
        params=mcp_types.CallToolRequestParams(name=name, arguments=arguments)
    )
    result = await handler(request)
    return result.root


@pytest.fixture(scope="session")
def database_url_or_skip() -> Iterator[str]:
    url = os.environ.get(ENV_DATABASE_URL)
    if not url:
        pytest.skip(f"{ENV_DATABASE_URL} unset; Postgres-backed tests skipped")
    yield url
