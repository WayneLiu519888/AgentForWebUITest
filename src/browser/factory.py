"""
BrowserFactory — 浏览器工厂

根据名称创建对应的浏览器实例。
"""

import logging
from typing import Optional

from .interface import BrowserInterface

logger = logging.getLogger(__name__)


def create_browser(
    name: str = "agent-browser",
    headless: bool = True,
    **kwargs,
) -> BrowserInterface:
    """创建浏览器实例

    根据名称路由到正确的浏览器实现。

    Args:
        name: 浏览器名称，可选:
            - "agent-browser" — 使用 agent-browser CLI (默认)
            - "chrome" / "chromium" — Playwright Chromium
            - "firefox" — Playwright Firefox
            - "webkit" — Playwright WebKit
        headless: 是否无头模式
        **kwargs: 传递给具体浏览器构造函数的额外参数

    Returns:
        BrowserInterface: 浏览器实例

    Raises:
        ValueError: 不支持的浏览器名称
        ImportError: 缺少必要的依赖

    Examples:
        >>> browser = create_browser("chromium", headless=True)
        >>> browser.navigate("https://example.com")
        >>> browser.close()

        >>> browser = create_browser("firefox", headless=False, viewport_width=1920)
    """
    name_lower = name.lower().strip()

    if name_lower == "agent-browser":
        # 使用 agent-browser CLI
        from .driver import AgentBrowser, BrowserConfig

        session_name = kwargs.pop("session_name", f"webui-test-{name_lower}")
        config = BrowserConfig(
            headless=headless,
            session_name=session_name,
            **kwargs,
        )
        return AgentBrowser(config)

    elif name_lower in ("chrome", "chromium", "firefox", "webkit"):
        # 使用 Playwright
        from .playwright_driver import PlaywrightBrowser

        return PlaywrightBrowser(
            browser_type=name_lower,
            headless=headless,
            **kwargs,
        )

    else:
        raise ValueError(
            f"不支持的浏览器: '{name}'。"
            f"可选: agent-browser, chrome, chromium, firefox, webkit"
        )


def list_available_browsers() -> list:
    """列出所有可用的浏览器类型

    Returns:
        list: 可用浏览器名称列表
    """
    available = ["agent-browser"]

    try:
        from .playwright_driver import HAS_PLAYWRIGHT
        if HAS_PLAYWRIGHT:
            available.extend(["chromium", "firefox", "webkit"])
        else:
            logger.debug("Playwright 未安装，仅 agent-browser 可用")
    except ImportError:
        pass

    return available
