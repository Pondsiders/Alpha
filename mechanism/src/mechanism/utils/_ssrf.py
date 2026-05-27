"""SSRF defense for outbound URL fetching.

Tools that take a user-supplied URL and make an HTTP request to it must
call `assert_public_url` first. Otherwise a malicious URL could target
internal services (Redis, Postgres, the MCP server itself, anything
else on workshop or the tailnet) that the mechanism process can
reach over the loopback or private network.

The check resolves the URL's host to IP addresses and rejects if any
resolved address is non-global (private, loopback, link-local,
reserved, multicast, or unspecified). The Tailscale CGNAT range
(100.64.0.0/10) is covered by `ipaddress.is_private` starting in
Python 3.12.

This is best-effort — a TOCTOU window exists between resolution here
and the actual request — but closes the easy-and-common attack
shapes (literal `http://localhost:6379`, `http://127.0.0.1:8000`,
hostnames that A-record to private IPs, etc.).
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from urllib.parse import urlparse


class SSRFError(Exception):
    """Raised when a URL is rejected by SSRF validation."""


async def assert_public_url(url: str) -> None:
    """Reject URLs that resolve to a non-public address.

    DNS resolution runs in a worker thread so a slow resolver doesn't
    stall the event loop while other tool calls are in flight.

    Args:
        url: The URL to validate.

    Raises:
        SSRFError: If the URL scheme isn't http or https, the URL has
            no hostname, DNS resolution fails, or any resolved IP is
            non-global.
    """
    parsed = urlparse(url)

    if parsed.scheme not in ("http", "https"):
        msg = f"URL scheme {parsed.scheme!r} not allowed; must be http or https"
        raise SSRFError(msg)

    host = parsed.hostname
    if not host:
        msg = f"URL has no hostname: {url!r}"
        raise SSRFError(msg)

    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as e:
        msg = f"DNS resolution failed for {host!r}: {e}"
        raise SSRFError(msg) from e

    for info in infos:
        addr = info[4][0]
        ip = ipaddress.ip_address(addr)
        if not ip.is_global:
            msg = f"URL {url!r} resolves to non-public address {addr}"
            raise SSRFError(msg)
