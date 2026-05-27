"""Integration tests for the utils `fetch` tool.

Outbound HTTP is mocked via `respx`. SSRF rejection runs against the
real DNS resolver but only for literal-IP and `localhost` inputs that
don't require network access. The mocked URLs all use `example.com`
(the IANA-reserved domain) so the SSRF pre-check resolves successfully
to a public IP before respx intercepts the actual GET.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, final, override

import httpx
import pytest
import respx
from fastmcp import Client
from fastmcp.exceptions import ToolError

from mechanism.utils import fetch as fetch_module
from mechanism.utils import mcp


async def _call_fetch(url: str) -> dict[str, Any]:
    async with Client(mcp) as client:
        result = await client.call_tool("fetch", {"url": url})
    assert result.structured_content is not None
    payload = result.structured_content
    # FastMCP returns Pydantic-model results with fields at the top level.
    if "content" in payload:
        return payload
    return payload["result"]


@respx.mock
async def test_tier1_accept_markdown_succeeds() -> None:
    """Tier 1 fires when the server returns text/markdown for an Accept: text/markdown request."""
    _ = respx.get("https://example.com/page").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/markdown; charset=utf-8"},
            text="# Heading\n\nBody paragraph.",
        )
    )
    payload = await _call_fetch("https://example.com/page")
    assert payload["content"] == "# Heading\n\nBody paragraph."
    assert payload["tier_used"] == "accept-markdown"
    assert payload["final_url"] == "https://example.com/page"


@respx.mock
async def test_tier2_url_variant_succeeds_for_html_url() -> None:
    """Tier 2 fires when /foo.html doesn't yield markdown but /foo.md does."""
    # Tier 1 path: HTML response, no markdown
    _ = respx.get("https://example.com/guide.html").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/html"},
            text="<html><body>html</body></html>",
        )
    )
    # Tier 2 path: variant URL has the markdown
    _ = respx.get("https://example.com/guide.md").mock(
        return_value=httpx.Response(
            200,
            headers={"content-type": "text/markdown"},
            text="# Guide\n\nVariant URL.",
        )
    )
    payload = await _call_fetch("https://example.com/guide.html")
    assert payload["content"] == "# Guide\n\nVariant URL."
    assert payload["tier_used"] == "url-variant"
    assert payload["final_url"] == "https://example.com/guide.md"


@respx.mock
async def test_tier3_trafilatura_extracts_from_html() -> None:
    """Tier 3 fires when tiers 1 and 2 both miss, and trafilatura extracts from HTML."""
    article_html = (
        "<html><head><title>Title</title></head><body>"
        "<nav>nav links</nav>"
        "<article><h1>Real Title</h1>"
        "<p>This is a substantial paragraph of real content that trafilatura "
        "should extract as the main body of the article. It needs to be long "
        "enough that the extractor recognizes it as article-shaped rather than "
        "chrome or boilerplate. Lorem ipsum dolor sit amet, consectetur "
        "adipiscing elit, sed do eiusmod tempor incididunt ut labore et dolore "
        "magna aliqua.</p>"
        "<p>A second paragraph helps trafilatura's content density heuristics "
        "decide this is the real article. Ut enim ad minim veniam, quis nostrud "
        "exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat.</p>"
        "</article>"
        "<footer>footer</footer>"
        "</body></html>"
    )
    # Tier 1 + Tier 3 both call GET on the same URL; respx returns the same
    # body on each match. The first call gets text/html (so tier 1 falls
    # through); the second call gets the same content for trafilatura to
    # extract from.
    _ = respx.get("https://example.com/article").mock(
        return_value=httpx.Response(200, headers={"content-type": "text/html"}, text=article_html)
    )
    # Tier 2 variants — return 404 so we fall through to tier 3
    _ = respx.get("https://example.com/article.md").mock(return_value=httpx.Response(404))
    _ = respx.get("https://example.com/article.mdx").mock(return_value=httpx.Response(404))

    payload = await _call_fetch("https://example.com/article")
    assert payload["tier_used"] == "trafilatura"
    # trafilatura output is markdown; should include some recognizable content
    content_lower = payload["content"].lower()
    assert "substantial paragraph" in content_lower or "real article" in content_lower


async def test_ssrf_rejects_loopback_url() -> None:
    """Literal http://127.0.0.1 must be rejected before any HTTP call goes out."""
    with pytest.raises(ToolError, match="non-public"):
        _ = await _call_fetch("http://127.0.0.1:8000/cortex/mcp")


async def test_ssrf_rejects_unsupported_scheme() -> None:
    """file:// or other schemes must be rejected."""
    with pytest.raises(ToolError, match="scheme"):
        _ = await _call_fetch("file:///etc/passwd")


@final
class _CountingByteStream(httpx.AsyncByteStream):
    """An async byte stream that records how many chunks it has yielded.

    Lets the oversized-body test assert that the fetcher bailed out
    mid-stream rather than buffering the whole body.
    """

    def __init__(self, chunk: bytes, n_chunks: int) -> None:
        self._chunk = chunk
        self._n_chunks = n_chunks
        self.chunks_yielded = 0

    @override
    async def __aiter__(self) -> AsyncIterator[bytes]:
        for _ in range(self._n_chunks):
            self.chunks_yielded += 1
            yield self._chunk

    @override
    async def aclose(self) -> None:
        return None


@respx.mock
async def test_oversized_body_without_content_length_is_rejected_mid_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A server that omits Content-Length must not be able to OOM us.

    Streams 1 KB chunks adding up to 64 KB with no Content-Length header,
    against a 4 KB ceiling. The fetcher must reject the response after a
    handful of chunks — *not* drain the whole body first.
    """
    monkeypatch.setattr(fetch_module, "_MAX_BODY_BYTES", 4 * 1024)

    chunk_size = 1024
    total_chunks = 64  # 64 KB per call — well over the 4 KB ceiling
    streams: list[_CountingByteStream] = []

    def make_response(request: httpx.Request) -> httpx.Response:  # pyright: ignore[reportUnusedParameter]
        # Fresh stream per call so each tier's GET starts from a full body.
        stream = _CountingByteStream(b"x" * chunk_size, total_chunks)
        streams.append(stream)
        return httpx.Response(200, headers={"content-type": "text/html"}, stream=stream)

    _ = respx.get("https://example.com/huge").mock(side_effect=make_response)
    # Tier 2 variants — return 404 so we fall through to tier 3 and then fail.
    _ = respx.get("https://example.com/huge.md").mock(return_value=httpx.Response(404))
    _ = respx.get("https://example.com/huge.mdx").mock(return_value=httpx.Response(404))

    with pytest.raises(ToolError, match="transport error or body too large"):
        _ = await _call_fetch("https://example.com/huge")

    # The fetcher hit the oversized URL at least once (tier 1 and tier 3
    # both call it). Every stream we handed out must have been abandoned
    # well before yielding all 64 chunks — proving the size check fires
    # mid-stream rather than after the whole body lands in memory.
    assert streams, "expected at least one streaming GET against /huge"
    for s in streams:
        assert s.chunks_yielded < total_chunks
        # Ceiling is 4 KB; with 1 KB chunks the fetcher needs at most 5
        # chunks (4 to reach the limit, 1 more to exceed it). Leave a
        # little headroom for httpx-internal buffering nuance.
        assert s.chunks_yielded <= 10
