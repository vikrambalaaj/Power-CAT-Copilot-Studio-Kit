"""HTTP helper utilities for MCP servers."""
from __future__ import annotations

import httpx


def create_async_client(timeout: float = 30.0) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout)
