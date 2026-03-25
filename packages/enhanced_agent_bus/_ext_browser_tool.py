# Constitutional Hash: 608508a9bd224290
"""Optional Lightpanda Browser Tool Integration."""

try:
    from .tools.browser_tool import (
        BrowserConfig,
        LightpandaBrowserTool,
        PageContent,
    )

    BROWSER_TOOL_AVAILABLE = True
except ImportError:
    BROWSER_TOOL_AVAILABLE = False
    BrowserConfig = object  # type: ignore[assignment, misc]
    LightpandaBrowserTool = object  # type: ignore[assignment, misc]
    PageContent = object  # type: ignore[assignment, misc]

_EXT_ALL = [
    "BROWSER_TOOL_AVAILABLE",
    "BrowserConfig",
    "LightpandaBrowserTool",
    "PageContent",
]
