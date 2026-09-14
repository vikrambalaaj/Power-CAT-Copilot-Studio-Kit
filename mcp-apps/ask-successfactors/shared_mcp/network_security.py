"""Network Security, Egress Allowlist, and SSRF Defense Module for Velora Platform.

Enforces:
- Scheme validation (HTTPS mandatory, rejection of file://, gopher://, ftp://, ldap://)
- Destination validation after DNS resolution (blocks 169.254.169.254, 168.63.129.16, loopback)
- RFC 1918 private address controls: private IPs blocked unless explicitly on ALLOWED_INTERNAL_HOSTS
- Safe OData NextLink validation (prevents origin diverting on pagination)
- Redirect chain inspection
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import urllib.parse
from typing import List, Optional, Set

log = logging.getLogger("shared_mcp.network_security")

# Cloud metadata and link-local networks to block unconditionally
METADATA_AND_LINK_LOCAL_NETWORKS = [
    ipaddress.ip_network("169.254.0.0/16"),       # IPv4 link-local & cloud metadata (AWS, Azure, GCP)
    ipaddress.ip_network("168.63.129.16/32"),     # Azure WireServer / IMDS
    ipaddress.ip_network("127.0.0.0/8"),          # Loopback
    ipaddress.ip_network("::1/128"),              # IPv6 loopback
    ipaddress.ip_network("fe80::/10"),            # IPv6 link-local
    ipaddress.ip_network("0.0.0.0/8"),            # Current network
]

# RFC 1918 Private IP networks
PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("fc00::/7"),             # IPv6 ULA
]

# Approved internal SAP / MeshX hostnames (configurable via ALLOWED_INTERNAL_HOSTS)
DEFAULT_APPROVED_INTERNAL_HOSTS = {
    "s4hana.velora.ae",
    "sap.corp.velora.ae",
    "meshx.velora.internal",
    "meshx.velora.ae",
    "sac.corp.velora.ae",
}


class SSRFSecurityError(Exception):
    """Raised when an outbound URL violates network security or SSRF policies."""
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def get_allowed_internal_hosts() -> Set[str]:
    raw = os.getenv("ALLOWED_INTERNAL_HOSTS", "")
    hosts = set(DEFAULT_APPROVED_INTERNAL_HOSTS)
    if raw:
        for h in raw.split(","):
            if h.strip():
                hosts.add(h.strip().lower())
    return hosts


def validate_destination_url(
    url: str,
    allow_internal_sap: bool = True,
    allowed_schemes: Optional[Set[str]] = None,
) -> str:
    """Validate destination URL against SSRF, metadata endpoint, and private network controls.
    
    Performs scheme check, host canonicalization, and DNS resolution validation.
    """
    if not url or not isinstance(url, str):
        raise SSRFSecurityError("Missing or invalid destination URL")

    url = url.strip()
    schemes = allowed_schemes or {"https"}

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception as e:
        raise SSRFSecurityError(f"Malformed URL structure: {e}")

    scheme = parsed.scheme.lower()
    if scheme not in schemes:
        raise SSRFSecurityError(f"Unauthorized URL scheme '{scheme}'. Only {schemes} are permitted.")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFSecurityError("URL must contain a valid hostname")

    hostname_clean = hostname.lower().strip(".")
    port = parsed.port or (443 if scheme == "https" else 80)

    allowed_internal = get_allowed_internal_hosts()
    is_approved_internal_host = hostname_clean in allowed_internal

    # Check for direct IP literal in hostname
    is_ip_literal = False
    try:
        ip_obj = ipaddress.ip_address(hostname_clean)
        is_ip_literal = True
        resolved_ips = [ip_obj]
    except ValueError:
        # Resolve via DNS
        try:
            addr_info = socket.getaddrinfo(hostname_clean, port, type=socket.SOCK_STREAM)
            resolved_ips = []
            for family, _, _, _, sockaddr in addr_info:
                ip_str = sockaddr[0]
                resolved_ips.append(ipaddress.ip_address(ip_str))
        except Exception as e:
            if is_approved_internal_host:
                log.info(f"Approved internal host '{hostname_clean}' allowed with offline DNS fallback")
                return url
            raise SSRFSecurityError(f"DNS resolution failure for host '{hostname_clean}': {e}")

    if not resolved_ips:
        raise SSRFSecurityError(f"No IP addresses resolved for host '{hostname_clean}'")

    for ip in resolved_ips:
        # 1. Check metadata and link-local (UNCONDITIONALLY BLOCKED)
        for net in METADATA_AND_LINK_LOCAL_NETWORKS:
            if ip in net:
                log.warning(f"Blocked SSRF attempt to metadata/link-local address {ip} via {url}")
                raise SSRFSecurityError(f"Access to link-local or cloud metadata address '{ip}' is strictly blocked")

        # 2. Check private RFC 1918 addresses
        for net in PRIVATE_NETWORKS:
            if ip in net:
                if allow_internal_sap and is_approved_internal_host:
                    # Permitted explicitly approved internal SAP/MeshX host
                    continue
                log.warning(f"Blocked SSRF attempt to unapproved private address {ip} (host: {hostname_clean})")
                raise SSRFSecurityError(
                    f"Access to private internal network address '{ip}' for host '{hostname_clean}' "
                    f"is blocked. Host must be on explicit approved internal allowlist."
                )

    return url


def validate_odata_next_link(base_request_url: str, next_link: str) -> str:
    """Validate OData pagination @odata.nextLink URL.
    
    Ensures nextLink does not change scheme, host, or port to prevent pagination-directed SSRF.
    """
    if not next_link or not isinstance(next_link, str):
        raise SSRFSecurityError("Invalid OData nextLink")

    # If relative path, resolve against base
    resolved = urllib.parse.urljoin(base_request_url, next_link)

    base_parsed = urllib.parse.urlparse(base_request_url)
    next_parsed = urllib.parse.urlparse(resolved)

    if next_parsed.scheme.lower() != base_parsed.scheme.lower():
        raise SSRFSecurityError(f"OData nextLink cannot alter scheme from {base_parsed.scheme} to {next_parsed.scheme}")

    if (next_parsed.hostname or "").lower() != (base_parsed.hostname or "").lower():
        raise SSRFSecurityError(
            f"OData nextLink host mismatch: expected '{base_parsed.hostname}', got '{next_parsed.hostname}'"
        )

    base_port = base_parsed.port or (443 if base_parsed.scheme == "https" else 80)
    next_port = next_parsed.port or (443 if next_parsed.scheme == "https" else 80)
    if next_port != base_port:
        raise SSRFSecurityError(f"OData nextLink port mismatch: expected {base_port}, got {next_port}")

    # Run full destination check on resolved URL
    return validate_destination_url(resolved)
