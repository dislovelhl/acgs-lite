"""
Tests for Lightpanda Browser Tool.

Mocks playwright to test tool logic without a running browser.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.fixture()
def mock_playwright():
    """Mock playwright async API."""
    mock_page = AsyncMock()
    mock_page.title = AsyncMock(return_value="Test Page")
    mock_page.inner_text = AsyncMock(return_value="Hello World content")
    mock_page.evaluate = AsyncMock(
        side_effect=[
            {"description": "A test page"},  # meta tags
            ["https://example.com/link1"],  # links
        ]
    )
    mock_page.set_default_timeout = MagicMock()

    mock_response = MagicMock()
    mock_response.status = 200
    mock_page.goto = AsyncMock(return_value=mock_response)

    mock_browser = AsyncMock()
    mock_browser.new_page = AsyncMock(return_value=mock_page)
    mock_browser.close = AsyncMock()

    mock_chromium = AsyncMock()
    mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

    mock_pw_instance = AsyncMock()
    mock_pw_instance.chromium = mock_chromium

    mock_pw_cm = AsyncMock()
    mock_pw_cm.__aenter__ = AsyncMock(return_value=mock_pw_instance)
    mock_pw_cm.__aexit__ = AsyncMock(return_value=False)

    return mock_pw_cm, mock_browser, mock_page


@pytest.fixture()
def _patch_playwright(mock_playwright):
    """Patch playwright in the browser_tool module."""
    mock_pw_cm, _, _ = mock_playwright
    with (
        patch(
            "enhanced_agent_bus.tools.browser_tool.HAS_PLAYWRIGHT",
            True,
        ),
        patch(
            "enhanced_agent_bus.tools.browser_tool.async_playwright",
            return_value=mock_pw_cm,
        ),
    ):
        yield


class TestLightpandaBrowserTool:
    """Tests for the browser tool."""

    @pytest.mark.usefixtures("_patch_playwright")
    def test_construction(self):
        from enhanced_agent_bus.tools.browser_tool import (
            BrowserConfig,
            LightpandaBrowserTool,
        )

        config = BrowserConfig(cdp_endpoint="ws://localhost:9222")
        tool = LightpandaBrowserTool(config=config)

        assert tool.stats["pages_fetched"] == 0
        assert tool.stats["errors"] == 0

    def test_construction_without_playwright_raises(self):
        with patch(
            "enhanced_agent_bus.tools.browser_tool.HAS_PLAYWRIGHT",
            False,
        ):
            from enhanced_agent_bus.tools.browser_tool import (
                LightpandaBrowserTool,
            )

            with pytest.raises(RuntimeError, match="playwright is not installed"):
                LightpandaBrowserTool()

    @pytest.mark.usefixtures("_patch_playwright")
    @pytest.mark.asyncio()
    async def test_fetch_page(self, mock_playwright):
        from enhanced_agent_bus.tools.browser_tool import (
            LightpandaBrowserTool,
        )

        tool = LightpandaBrowserTool()
        content = await tool.fetch_page("https://example.com")

        assert content.url == "https://example.com"
        assert content.title == "Test Page"
        assert content.text == "Hello World content"
        assert content.status == 200
        assert content.latency_ms > 0
        assert not content.truncated
        assert tool.stats["pages_fetched"] == 1

    @pytest.mark.usefixtures("_patch_playwright")
    @pytest.mark.asyncio()
    async def test_fetch_page_extracts_meta(self, mock_playwright):
        from enhanced_agent_bus.tools.browser_tool import (
            LightpandaBrowserTool,
        )

        tool = LightpandaBrowserTool()
        content = await tool.fetch_page("https://example.com")

        assert "description" in content.meta

    @pytest.mark.usefixtures("_patch_playwright")
    @pytest.mark.asyncio()
    async def test_fetch_page_extracts_links(self, mock_playwright):
        from enhanced_agent_bus.tools.browser_tool import (
            LightpandaBrowserTool,
        )

        tool = LightpandaBrowserTool()
        content = await tool.fetch_page("https://example.com")

        assert len(content.links) == 1
        assert content.links[0] == "https://example.com/link1"

    @pytest.mark.usefixtures("_patch_playwright")
    @pytest.mark.asyncio()
    async def test_fetch_page_truncation(self, mock_playwright):
        from enhanced_agent_bus.tools.browser_tool import (
            BrowserConfig,
            LightpandaBrowserTool,
        )

        _, _, mock_page = mock_playwright
        mock_page.inner_text = AsyncMock(return_value="x" * 100)

        config = BrowserConfig(max_content_length=50)
        tool = LightpandaBrowserTool(config=config)
        content = await tool.fetch_page("https://example.com")

        assert len(content.text) == 50
        assert content.truncated

    @pytest.mark.usefixtures("_patch_playwright")
    @pytest.mark.asyncio()
    async def test_fetch_text_convenience(self, mock_playwright):
        from enhanced_agent_bus.tools.browser_tool import (
            LightpandaBrowserTool,
        )

        tool = LightpandaBrowserTool()
        text = await tool.fetch_text("https://example.com")

        assert text == "Hello World content"

    @pytest.mark.asyncio()
    async def test_fetch_page_error_tracking(self):
        """Test that errors are tracked in stats."""
        with (
            patch(
                "enhanced_agent_bus.tools.browser_tool.HAS_PLAYWRIGHT",
                True,
            ),
            patch(
                "enhanced_agent_bus.tools.browser_tool.async_playwright",
                side_effect=ConnectionError("no browser"),
            ),
        ):
            from enhanced_agent_bus.tools.browser_tool import (
                LightpandaBrowserTool,
            )

            tool = LightpandaBrowserTool()

            with pytest.raises(ConnectionError):
                await tool.fetch_page("https://example.com")

            assert tool.stats["errors"] == 1


class TestBrowserConfig:
    """Test browser configuration."""

    def test_default_config(self):
        from enhanced_agent_bus.tools.browser_tool import BrowserConfig

        config = BrowserConfig()
        assert config.cdp_endpoint == "ws://127.0.0.1:9222"
        assert config.max_content_length == 50_000
        assert not config.use_local_binary

    def test_custom_config(self):
        from enhanced_agent_bus.tools.browser_tool import BrowserConfig

        config = BrowserConfig(
            cdp_endpoint="ws://lightpanda:9222",
            max_content_length=10_000,
            use_local_binary=True,
        )
        assert config.cdp_endpoint == "ws://lightpanda:9222"
        assert config.max_content_length == 10_000


class TestPageContent:
    """Test page content dataclass."""

    def test_page_content_creation(self):
        from enhanced_agent_bus.tools.browser_tool import PageContent

        content = PageContent(
            url="https://example.com",
            title="Test",
            text="Content",
            status=200,
        )
        assert content.url == "https://example.com"
        assert content.meta == {}
        assert content.links == []
        assert not content.truncated
