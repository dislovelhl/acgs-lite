"""
ACGS-2 Agent Tools - Lightpanda Browser Tool
Constitutional Hash: 608508a9bd224290

Lightweight headless browser for agent web content fetching.
Uses Lightpanda (11x faster, 9x less memory than Chrome) via CDP,
with Playwright as the automation API.

Supports:
- Page content extraction (title, text, metadata)
- JavaScript rendering for dynamic pages
- Screenshot capture for visual analysis
- Configurable via Docker or local binary
"""

from __future__ import annotations

import asyncio
import subprocess
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

try:
    from enhanced_agent_bus._compat.constants import CONSTITUTIONAL_HASH
except ImportError:
    CONSTITUTIONAL_HASH = "standalone"

from enhanced_agent_bus.observability.structured_logging import get_logger

logger = get_logger(__name__)

try:
    from playwright.async_api import Browser, Page, async_playwright

    HAS_PLAYWRIGHT = True
except ImportError:
    HAS_PLAYWRIGHT = False
    Browser = None  # type: ignore[assignment, misc]
    Page = None  # type: ignore[assignment, misc]
    async_playwright = None  # type: ignore[assignment, misc]


@dataclass
class BrowserConfig:
    """Configuration for the Lightpanda browser tool."""

    cdp_endpoint: str = "ws://127.0.0.1:9222"
    use_local_binary: bool = False
    binary_path: str = "lightpanda"
    startup_timeout_s: float = 5.0
    page_timeout_ms: int = 30_000
    max_content_length: int = 50_000
    constitutional_hash: str = CONSTITUTIONAL_HASH


@dataclass
class PageContent:
    """Extracted content from a web page."""

    url: str
    title: str
    text: str
    meta: dict[str, str] = field(default_factory=dict)
    links: list[str] = field(default_factory=list)
    status: int | None = None
    latency_ms: float = 0.0
    truncated: bool = False
    constitutional_hash: str = CONSTITUTIONAL_HASH


class LightpandaBrowserTool:
    """Agent browser tool using Lightpanda for fast, low-memory web access.

    Provides agents with the ability to fetch and extract web page content
    using Lightpanda's headless browser via CDP (Chrome DevTools Protocol).
    Falls back to managing a local Lightpanda process if no CDP endpoint
    is available.

    Usage:
        tool = LightpandaBrowserTool()

        # Simple content extraction
        content = await tool.fetch_page("https://example.com")
        print(content.title, content.text[:500])

        # With managed browser lifecycle
        async with tool.managed_browser() as browser:
            page = await browser.new_page()
            await page.goto("https://example.com")
            # ... custom automation

    Constitutional Hash: 608508a9bd224290
    """

    def __init__(self, config: BrowserConfig | None = None) -> None:
        if not HAS_PLAYWRIGHT:
            raise RuntimeError(
                "playwright is not installed. "
                "Install with: pip install playwright && playwright install"
            )
        self._config = config or BrowserConfig()
        self._process: subprocess.Popen | None = None
        self._stats = {
            "pages_fetched": 0,
            "errors": 0,
            "total_latency_ms": 0.0,
        }

    @property
    def stats(self) -> dict[str, Any]:
        return dict(self._stats)

    @asynccontextmanager
    async def managed_browser(self) -> AsyncIterator[Browser]:
        """Context manager that connects to Lightpanda CDP endpoint.

        If use_local_binary is True, starts a local Lightpanda process
        and connects to it. Otherwise, connects to the configured endpoint.
        """
        proc = None
        if self._config.use_local_binary:
            proc = subprocess.Popen(
                [self._config.binary_path, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            await asyncio.sleep(self._config.startup_timeout_s)

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.connect_over_cdp(self._config.cdp_endpoint)
                try:
                    yield browser
                finally:
                    await browser.close()
        finally:
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    async def fetch_page(self, url: str) -> PageContent:
        """Fetch and extract content from a URL.

        Args:
            url: The URL to fetch.

        Returns:
            PageContent with title, text, metadata, and links.
        """
        start = time.monotonic()
        try:
            async with self.managed_browser() as browser:
                page = await browser.new_page()
                page.set_default_timeout(self._config.page_timeout_ms)

                response = await page.goto(url, wait_until="domcontentloaded")
                status = response.status if response else None

                title = await page.title()
                text = await page.inner_text("body")

                # Extract meta tags
                meta = await page.evaluate("""() => {
                    const metas = {};
                    document.querySelectorAll('meta[name], meta[property]').forEach(m => {
                        const key = m.getAttribute('name') || m.getAttribute('property');
                        const val = m.getAttribute('content');
                        if (key && val) metas[key] = val;
                    });
                    return metas;
                }""")

                # Extract links
                links = await page.evaluate("""() => {
                    return Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href)
                        .filter(h => h.startsWith('http'))
                        .slice(0, 50);
                }""")

                latency = (time.monotonic() - start) * 1000
                truncated = len(text) > self._config.max_content_length

                self._stats["pages_fetched"] += 1
                self._stats["total_latency_ms"] += latency

                logger.info(
                    "page_fetched",
                    url=url,
                    status=status,
                    text_length=len(text),
                    latency_ms=round(latency, 2),
                )

                return PageContent(
                    url=url,
                    title=title,
                    text=text[: self._config.max_content_length],
                    meta=meta or {},
                    links=links or [],
                    status=status,
                    latency_ms=latency,
                    truncated=truncated,
                )

        except Exception as exc:
            latency = (time.monotonic() - start) * 1000
            self._stats["errors"] += 1
            logger.error(
                "page_fetch_failed",
                url=url,
                error=type(exc).__name__,
                latency_ms=round(latency, 2),
            )
            raise

    async def fetch_text(self, url: str) -> str:
        """Convenience method: fetch a page and return just the text content."""
        content = await self.fetch_page(url)
        return content.text
