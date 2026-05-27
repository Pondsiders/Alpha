"""The `fetch` tool — URL → Markdown via a three-tier strategy."""

from __future__ import annotations

import asyncio
from typing import Annotated
from urllib.parse import urlparse

import httpx
import trafilatura
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from mechanism.utils._ssrf import SSRFError, assert_public_url
from mechanism.utils.models import FetchResult
from mechanism.utils.server import mcp

_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
_MAX_BODY_BYTES = 5 * 1024 * 1024  # 5 MB ceiling on response body


async def _get(url: str, *, headers: dict[str, str] | None = None) -> httpx.Response | None:
    """GET with our standard timeout + size guard. Returns None on transport or size failure.

    The size guard runs *during* the download: bytes are streamed and
    accumulated chunk by chunk, and the response is rejected the moment
    the running total exceeds `_MAX_BODY_BYTES`. This bounds memory at
    the ceiling even when the server omits Content-Length.
    """
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        try:
            async with client.stream("GET", url, headers=headers) as resp:
                # Honor an honest Content-Length up front — avoid even starting
                # to buffer a body the server has already declared too large.
                content_length = resp.headers.get("content-length")
                if content_length is not None:
                    try:
                        if int(content_length) > _MAX_BODY_BYTES:
                            return None
                    except ValueError:
                        pass

                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > _MAX_BODY_BYTES:
                        return None
                # Hand the accumulated body to the Response so downstream
                # callers can use .text / .content as usual after the stream
                # context exits.
                body = bytes(buf)
        except httpx.HTTPError:
            return None

    resp._content = body  # pyright: ignore[reportPrivateUsage]
    return resp


async def _fetch_with_accept_markdown(url: str) -> tuple[str, str] | None:
    """Tier 1: send Accept: text/markdown; succeed if the server gives us markdown."""
    resp = await _get(url, headers={"Accept": "text/markdown"})
    if resp is None or resp.status_code != 200:
        return None
    content_type = resp.headers.get("content-type", "").lower()
    if "text/markdown" not in content_type:
        return None
    return resp.text, str(resp.url)


async def _fetch_url_variants(url: str) -> tuple[str, str] | None:
    """Tier 2: try common markdown-variant URLs (.md, .mdx) for the same resource."""
    parsed = urlparse(url)
    path = parsed.path.rstrip("/")
    candidates: list[str] = []

    if path.endswith(".html"):
        stem = path[: -len(".html")]
        candidates.append(stem + ".md")
        candidates.append(stem + ".mdx")
    elif "." not in path.rsplit("/", 1)[-1]:
        # Path has no extension on the last segment — try appending .md/.mdx.
        candidates.append(path + ".md")
        candidates.append(path + ".mdx")

    for candidate_path in candidates:
        candidate_url = parsed._replace(path=candidate_path).geturl()
        resp = await _get(candidate_url)
        if resp is None or resp.status_code != 200:
            continue
        if not resp.text.strip():
            continue
        return resp.text, str(resp.url)

    return None


async def _fetch_and_extract(url: str) -> tuple[str, str]:
    """Tier 3: GET the page as HTML, extract Markdown via trafilatura."""
    resp = await _get(url)
    if resp is None:
        msg = f"fetch failed: transport error or body too large for {url}"
        raise ToolError(msg)
    if resp.status_code != 200:
        msg = f"fetch failed: status {resp.status_code} for {url}"
        raise ToolError(msg)

    html = resp.text
    final_url = str(resp.url)

    # trafilatura.extract is sync; offload to a thread so the event loop isn't blocked.
    markdown = await asyncio.to_thread(
        trafilatura.extract,
        html,
        output_format="markdown",
        include_links=True,
        include_tables=True,
        include_images=False,
    )
    if markdown is None or not markdown.strip():
        msg = f"trafilatura extracted no usable content from {url}"
        raise ToolError(msg)
    return markdown, final_url


@mcp.tool(
    description=(
        "Fetch a URL and return its content as clean Markdown. Tries three "
        "tiers in order: (1) Accept: text/markdown header — works for "
        "Cloudflare-rendered sites and many doc generators; (2) URL variants "
        "like /foo -> /foo.md — works for Mintlify and similar; (3) HTML "
        "extraction via trafilatura."
    ),
    annotations=ToolAnnotations(
        title="Fetch URL -> Markdown",
        readOnlyHint=True,
        openWorldHint=True,
    ),
    meta={
        "anthropic/maxResultSizeChars": 400000,
        "anthropic/alwaysLoad": True,
    },
)
async def fetch(
    url: Annotated[
        str,
        Field(
            description=(
                "The URL to fetch. Must be http or https. URLs that resolve to "
                "private, loopback, link-local, or otherwise non-public addresses "
                "are rejected to prevent SSRF against internal services."
            ),
        ),
    ],
) -> FetchResult:
    """Fetch a URL and return its content as clean Markdown.

    Args:
        url: The URL to fetch.

    Returns:
        The extracted content, the final URL after redirects, and which
        tier produced the content.

    Raises:
        ToolError: If the URL is rejected by SSRF validation, the server is
            unreachable, or no tier can produce usable content.
    """
    try:
        await assert_public_url(url)
    except SSRFError as e:
        raise ToolError(str(e)) from e

    # Tier 1: Accept: text/markdown
    tier1 = await _fetch_with_accept_markdown(url)
    if tier1 is not None:
        content, final_url = tier1
        return FetchResult(content=content, final_url=final_url, tier_used="accept-markdown")

    # Tier 2: URL variants
    tier2 = await _fetch_url_variants(url)
    if tier2 is not None:
        content, final_url = tier2
        return FetchResult(content=content, final_url=final_url, tier_used="url-variant")

    # Tier 3: HTML extraction (raises ToolError if it fails)
    content, final_url = await _fetch_and_extract(url)
    return FetchResult(content=content, final_url=final_url, tier_used="trafilatura")
