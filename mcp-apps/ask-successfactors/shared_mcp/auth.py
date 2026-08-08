"""Authentication helper placeholders for shared MCP utilities."""
from __future__ import annotations


def get_auth_header(token: str | None) -> dict[str, str]:
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}
