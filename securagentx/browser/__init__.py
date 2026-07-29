"""SecurAgentX browser automation — Playwright-based web interaction.

This subpackage exposes :class:`BrowserTool`, an async wrapper around
Playwright that drives a real headless Chromium for navigation, clicking,
typing, screenshotting, and content extraction. Playwright is an *optional*
dependency — install it with::

    pip install -e .[browser]
    playwright install chromium

The module imports cleanly even when Playwright is absent; the
:class:`BrowserTool` instance only raises an error when an action is
actually invoked (see :meth:`BrowserTool.is_available`).
"""
from .browser_tool import BrowserAction, BrowserTool

__all__ = ["BrowserTool", "BrowserAction"]
