"""Kill Switch and Circuit Breaker Module for Velora Platform.

Enforces WP12 / AIDEV-27 requirements:
- Global immediate kill switch: stops all AI agent executions immediately
- Per-tool kill switch: disables specific tools (e.g. email sending, calendar writes)
- Per-client / Per-tenant kill switch: isolates rogue clients or compromised tenants
- Zero downtime evaluation immediately prior to business execution
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional, Set

log = logging.getLogger("shared_mcp.kill_switch")


class KillSwitchActiveError(Exception):
    """Raised when an operation is blocked by an active kill switch."""
    def __init__(self, message: str = "Operation disabled by security kill switch"):
        super().__init__(message)
        self.message = message


def is_global_kill_switch_active() -> bool:
    """Check if the global emergency kill switch is engaged."""
    if os.getenv("VELORA_EMERGENCY_KILL_SWITCH", "").lower() in ("1", "true", "yes"):
        return True

    # Check for file-based signal (useful for zero-restart operations in container volume)
    kill_file_paths = [
        Path("/etc/velora/kill_switch"),
        Path(os.getenv("VELORA_STATE_DIR", "/mnt/velora/state")) / "kill_switch",
        Path.home() / ".velora" / "kill_switch",
    ]
    for p in kill_file_paths:
        try:
            if p.exists():
                return True
        except Exception:
            pass

    return False


def get_disabled_tools() -> Set[str]:
    """Retrieve the set of dynamically disabled tools."""
    raw = os.getenv("DISABLED_TOOLS", "")
    disabled = set()
    if raw:
        for t in raw.split(","):
            if t.strip():
                disabled.add(t.strip().lower())
    return disabled


def get_disabled_clients() -> Set[str]:
    """Retrieve the set of dynamically disabled client IDs."""
    raw = os.getenv("DISABLED_CLIENTS", "")
    disabled = set()
    if raw:
        for c in raw.split(","):
            if c.strip():
                disabled.add(c.strip().lower())
    return disabled


def get_disabled_tenants() -> Set[str]:
    """Retrieve the set of dynamically disabled tenant IDs."""
    raw = os.getenv("DISABLED_TENANTS", "")
    disabled = set()
    if raw:
        for t in raw.split(","):
            if t.strip():
                disabled.add(t.strip().lower())
    return disabled


def check_kill_switch(
    tool_name: Optional[str] = None,
    client_id: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> None:
    """Evaluate all kill switch tiers. Raises KillSwitchActiveError if blocked."""
    # 1. Global Kill Switch
    if is_global_kill_switch_active():
        log.critical("Execution BLOCKED: Global Velora emergency kill switch is ACTIVE.")
        raise KillSwitchActiveError("Velora Platform operations are currently paused by emergency kill switch.")

    # 2. Per-Tool Kill Switch
    if tool_name:
        disabled_tools = get_disabled_tools()
        if tool_name.strip().lower() in disabled_tools:
            log.warning(f"Execution BLOCKED: Tool '{tool_name}' is disabled via DISABLED_TOOLS.")
            raise KillSwitchActiveError(f"Tool '{tool_name}' has been temporarily disabled by administrative policy.")

    # 3. Per-Client Kill Switch
    if client_id:
        disabled_clients = get_disabled_clients()
        if client_id.strip().lower() in disabled_clients:
            log.warning(f"Execution BLOCKED: Client application '{client_id}' is disabled via DISABLED_CLIENTS.")
            raise KillSwitchActiveError(f"Client application '{client_id}' is temporarily blocked from invoking tools.")

    # 4. Per-Tenant Kill Switch
    if tenant_id:
        disabled_tenants = get_disabled_tenants()
        if tenant_id.strip().lower() in disabled_tenants:
            log.warning(f"Execution BLOCKED: Tenant '{tenant_id}' is disabled via DISABLED_TENANTS.")
            raise KillSwitchActiveError(f"Tenant '{tenant_id}' operations are temporarily suspended.")


def set_kill_switch(tier: str, value: str = "true") -> None:
    """Convenience helper to activate a kill switch tier."""
    t = tier.lower()
    if t == "global":
        os.environ["VELORA_EMERGENCY_KILL_SWITCH"] = "true"
    elif t in ("tool", "tools"):
        curr = os.getenv("DISABLED_TOOLS", "")
        items = set(x.strip().lower() for x in curr.split(",") if x.strip())
        items.add(value.strip().lower())
        os.environ["DISABLED_TOOLS"] = ",".join(items)
    elif t in ("client", "clients"):
        curr = os.getenv("DISABLED_CLIENTS", "")
        items = set(x.strip().lower() for x in curr.split(",") if x.strip())
        items.add(value.strip().lower())
        os.environ["DISABLED_CLIENTS"] = ",".join(items)
    elif t in ("tenant", "tenants"):
        curr = os.getenv("DISABLED_TENANTS", "")
        items = set(x.strip().lower() for x in curr.split(",") if x.strip())
        items.add(value.strip().lower())
        os.environ["DISABLED_TENANTS"] = ",".join(items)


def clear_all_kill_switches() -> None:
    """Clear all kill switch environment overrides."""
    os.environ.pop("VELORA_EMERGENCY_KILL_SWITCH", None)
    os.environ.pop("DISABLED_TOOLS", None)
    os.environ.pop("DISABLED_CLIENTS", None)
    os.environ.pop("DISABLED_TENANTS", None)

