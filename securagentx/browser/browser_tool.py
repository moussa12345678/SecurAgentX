"""securagentx/browser/browser_tool.py — Playwright-based browser automation.

Architecture (inspired by :mod:`securagentx.docker.browser` — the
sidecar-based scraper — but Python-native and sidecar-free):

* :class:`BrowserTool` is an *async* wrapper around Playwright's
  ``async_api``. A single Chromium instance is launched lazily on the
  first action and reused across calls until :meth:`BrowserTool.close`
  is invoked (or the async context manager exits).
* Headless by default — CI-safe.
* All URLs are validated with :func:`securagentx.utils.url.validate_url_scheme`
  (http/https only) to prevent ``file://`` SSRF-style abuse.
* TLS verification is ON by default. Set ``SECURAGENTX_INSECURE=1`` to
  opt out (mirrors :mod:`securagentx.docker.browser`).
* Screenshot capture returns raw PNG ``bytes`` so callers can feed it
  directly to a VLM (see :meth:`BrowserTool.analyze_screenshot_with_vlm`).
* Playwright is *lazy-imported* — the module imports cleanly even when
  Playwright is not installed, so AST-level test discovery still works.
  :meth:`BrowserTool.is_available` reports the runtime availability.

The 8 supported actions are enumerated in :class:`BrowserAction`:

    ================== =====================================================
    Action             Effect
    ================== =====================================================
    ``NAVIGATE``       Open ``url`` and wait for ``load`` event.
    ``CLICK``          Click the element at ``selector``.
    ``TYPE``           Type ``text`` into the element at ``selector``.
    ``SCREENSHOT``     Capture a full-page PNG of ``url`` (or current page).
    ``CONTENT_MD``     Extract page content as Markdown (trafilatura).
    ``CONTENT_HTML``   Extract raw ``page.content()`` HTML.
    ``LINKS``          Extract all ``<a href>`` links on the page.
    ``FORM_SUBMIT``    Submit the form at ``selector`` (or first form).
    ================== =====================================================
"""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from enum import Enum
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin, urlparse

from securagentx.utils.url import validate_url_scheme

logger = logging.getLogger("securagentx.browser")

# ── TLS verification toggle (mirrors securagentx/docker/browser.py) ───────
# Issue 32 (P8-C): TLS verification is ON by default. Set
# SECURAGENTX_INSECURE=1|true|yes to opt into verify=False for self-signed
# or internal-test targets.
INSECURE = os.environ.get("SECURAGENTX_INSECURE", "").lower() in (
    "1", "true", "yes",
)

# Default page-load timeout in milliseconds.
DEFAULT_TIMEOUT_MS = 30_000

# Maximum content size returned in dicts (avoids 10MB HTML blowing up the
# agent context window). Callers wanting raw HTML should use the
# ``get_content_html`` method directly and accept the truncation.
_MAX_CONTENT_CHARS = 50_000

# Maximum number of links returned by ``get_links`` to keep payloads sane.
_MAX_LINKS = 500


class BrowserAction(str, Enum):
    """Supported browser actions.

    Inherits ``str`` so the value can be compared/sent over the wire as a
    plain string (e.g. ``BrowserAction.NAVIGATE == "navigate"``).
    """

    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE = "type"
    SCREENSHOT = "screenshot"
    CONTENT_MD = "content_md"
    CONTENT_HTML = "content_html"
    LINKS = "links"
    FORM_SUBMIT = "form_submit"


def _resolve_action(action: str) -> BrowserAction:
    """Map a free-form string to a :class:`BrowserAction`.

    Accepts the enum value (``"navigate"``), the enum name
    (``"NAVIGATE"``), or an actual :class:`BrowserAction` instance.
    Raises ``ValueError`` for unknown actions.
    """
    if isinstance(action, BrowserAction):
        return action
    key = action.strip()
    # Match by value first (case-insensitive), then by name (upper-case).
    try:
        return BrowserAction(key.lower())
    except ValueError:
        pass
    try:
        return BrowserAction[key.upper()]
    except KeyError as exc:
        raise ValueError(f"unknown browser action: {action!r}") from exc


class BrowserTool:
    """Async Playwright wrapper with lazy browser launch.

    Usage (async)::

        async with BrowserTool(headless=True) as browser:
            result = await browser.handle("navigate", url="https://example.com")
            md = await browser.get_content_markdown("https://example.com")
            png = await browser.screenshot("https://example.com")

    The class is also usable without a context manager — just remember to
    ``await browser.close()`` when finished::

        browser = BrowserTool()
        try:
            await browser.handle("navigate", url="https://example.com")
        finally:
            await browser.close()

    All public methods return ``dict`` objects with the keys ``success``,
    ``output`` and ``screenshot`` (the screenshot key is ``None`` when no
    screenshot was captured, otherwise a base64-encoded PNG string — raw
    bytes are available via :meth:`screenshot`).
    """

    def __init__(self, headless: bool = True, timeout: int = DEFAULT_TIMEOUT_MS) -> None:
        self.headless = headless
        self.timeout = timeout
        # Lazy-init — these are populated on the first action.
        self._playwright = None  # type: ignore[assignment]
        self._browser = None  # type: ignore[assignment]
        self._context = None  # type: ignore[assignment]
        self._page = None  # type: ignore[assignment]
        self._closed = False

    # ── Availability probe ─────────────────────────────────────────────
    def is_available(self) -> bool:
        """Return True iff Playwright is importable.

        Note: this does *not* check that a browser binary is installed
        (``playwright install chromium``). A ``RuntimeError`` from
        Playwright on first action likely means the binary is missing.
        """
        try:
            import playwright  # type: ignore[import-not-found]  # noqa: F401
            import playwright.async_api  # type: ignore[import-not-found]  # noqa: F401
            return True
        except ImportError:
            return False

    # ── Lazy browser launch ───────────────────────────────────────────
    async def _ensure_browser(self) -> None:
        """Launch Chromium on first use.

        Idempotent — subsequent calls reuse the existing browser/context/page.
        Raises ``RuntimeError`` if Playwright is not installed.
        """
        if self._page is not None:
            return
        if self._closed:
            raise RuntimeError("BrowserTool has been closed; create a new instance.")

        try:
            from playwright.async_api import async_playwright
        except ImportError as exc:  # pragma: no cover — runtime guard
            raise RuntimeError(
                "Playwright is not installed. Install with: "
                "pip install -e .[browser] && playwright install chromium"
            ) from exc

        logger.debug(
            "launching chromium (headless=%s, timeout=%dms, insecure=%s)",
            self.headless, self.timeout, INSECURE,
        )
        self._playwright = await async_playwright().start()  # type: ignore[assignment]
        # ``ignore_https_errors`` honours SECURAGENTX_INSECURE.
        self._browser = await self._playwright.chromium.launch(  # type: ignore[attr-defined]
            headless=self.headless,
            args=["--no-sandbox"] if os.environ.get("SECURAGENTX_BROWSER_NO_SANDBOX") else [],
        )
        self._context = await self._browser.new_context(  # type: ignore[attr-defined]
            ignore_https_errors=INSECURE,
            viewport={"width": 1280, "height": 720},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 "
                "SecurAgentX/BrowserTool"
            ),
        )
        self._context.set_default_timeout(self.timeout)  # type: ignore[attr-defined]
        self._context.set_default_navigation_timeout(self.timeout)  # type: ignore[attr-defined]
        self._page = await self._context.new_page()  # type: ignore[attr-defined]

    @property
    def page(self):  # type: ignore[no-untyped-def]
        """The current Playwright Page (``None`` before first action)."""
        return self._page

    # ── URL validation helper ─────────────────────────────────────────
    @staticmethod
    def _validate_url(url: str) -> str:
        """Validate URL scheme via :func:`validate_url_scheme`.

        Empty URLs are rejected (callers should pass the current page URL
        when an action is meant to reuse the existing page).
        """
        if not url or not url.strip():
            raise ValueError("a non-empty url is required")
        return validate_url_scheme(url.strip())

    # ── Main dispatcher ───────────────────────────────────────────────
    async def handle(
        self,
        action: str,
        url: str = "",
        selector: str = "",
        text: str = "",
    ) -> Dict[str, Any]:
        """Dispatch a browser action by name.

        Parameters mirror the union of all action signatures:

        * ``url`` — required for NAVIGATE, SCREENSHOT, CONTENT_MD,
          CONTENT_HTML, LINKS. Ignored (optional) for CLICK, TYPE,
          FORM_SUBMIT which operate on the current page.
        * ``selector`` — required for CLICK, TYPE, FORM_SUBMIT.
        * ``text`` — required for TYPE.

        Returns a dict with ``success``, ``output`` (string),
        ``screenshot`` (base64 PNG or ``None``), and action-specific
        extra keys (e.g. ``url``, ``title``, ``links``).
        """
        resolved = _resolve_action(action)
        logger.info("browser action: %s (url=%r selector=%r)", resolved.value, url, selector)

        try:
            if resolved is BrowserAction.NAVIGATE:
                return await self.navigate(url)
            if resolved is BrowserAction.CLICK:
                return await self.click(selector)
            if resolved is BrowserAction.TYPE:
                return await self.type_text(selector, text)
            if resolved is BrowserAction.SCREENSHOT:
                png = await self.screenshot(url)
                return self._ok(
                    output=f"Captured {len(png)} bytes PNG",
                    screenshot=png,
                    extra={"bytes": len(png)},
                )
            if resolved is BrowserAction.CONTENT_MD:
                md = await self.get_content_markdown(url)
                return self._ok(output=md)
            if resolved is BrowserAction.CONTENT_HTML:
                html = await self.get_content_html(url)
                return self._ok(output=html)
            if resolved is BrowserAction.LINKS:
                links = await self.get_links(url)
                return self._ok(
                    output=f"Extracted {len(links)} links",
                    extra={"links": links},
                )
            if resolved is BrowserAction.FORM_SUBMIT:
                return await self.form_submit(selector)
            # Unreachable — _resolve_action raises first.
            raise ValueError(f"unhandled action: {resolved}")
        except Exception as exc:  # noqa: BLE001 — central error capture
            logger.error("browser action %s failed: %s", resolved.value, exc)
            return {
                "success": False,
                "error": str(exc),
                "output": "",
                "screenshot": None,
                "action": resolved.value,
            }

    # ── Individual actions ────────────────────────────────────────────
    async def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to ``url`` and wait for the ``load`` event.

        Returns the resolved URL and page title.
        """
        url = self._validate_url(url)
        await self._ensure_browser()
        assert self._page is not None  # for type-checkers
        response = await self._page.goto(url, wait_until="load", timeout=self.timeout)
        title = await self._page.title()
        status = response.status if response is not None else 0
        logger.info("navigated to %s (status=%d, title=%r)", url, status, title)
        return self._ok(
            output=f"Navigated to {url} (HTTP {status}) — title: {title}",
            extra={"url": url, "title": title, "status": status},
        )

    async def click(self, selector: str) -> Dict[str, Any]:
        """Click the element matching ``selector`` (CSS/XPath)."""
        if not selector:
            raise ValueError("a non-empty selector is required for click")
        await self._ensure_browser()
        assert self._page is not None
        await self._page.click(selector, timeout=self.timeout)
        logger.info("clicked %s", selector)
        return self._ok(output=f"Clicked element: {selector}", extra={"selector": selector})

    async def type_text(self, selector: str, text: str) -> Dict[str, Any]:
        """Type ``text`` into the element at ``selector``.

        Uses ``fill`` (clears the field first) which is the safer default
        for form-filling automation.
        """
        if not selector:
            raise ValueError("a non-empty selector is required for type")
        if text is None:
            raise ValueError("text is required for type")
        await self._ensure_browser()
        assert self._page is not None
        await self._page.fill(selector, text, timeout=self.timeout)
        logger.info("typed %d chars into %s", len(text), selector)
        return self._ok(
            output=f"Typed {len(text)} chars into {selector}",
            extra={"selector": selector, "chars": len(text)},
        )

    async def screenshot(self, url: str = "") -> bytes:
        """Capture a full-page PNG screenshot.

        If ``url`` is provided, the browser navigates to it first
        (validated via :func:`validate_url_scheme`). Otherwise the current
        page is captured. Returns raw PNG ``bytes``.
        """
        await self._ensure_browser()
        assert self._page is not None
        if url:
            url = self._validate_url(url)
            await self._page.goto(url, wait_until="load", timeout=self.timeout)
        png = await self._page.screenshot(full_page=True, type="png")
        logger.info("captured %d byte PNG", len(png))
        return png

    async def get_content_markdown(self, url: str) -> str:
        """Extract page content as Markdown.

        Navigation is performed with Playwright (so JS-rendered pages are
        captured), then the resulting HTML is converted to Markdown using
        ``trafilatura`` (already a hard dep). Falls back to a simple
        ``innerText`` dump if trafilatura is unavailable.
        """
        url = self._validate_url(url)
        await self._ensure_browser()
        assert self._page is not None
        await self._page.goto(url, wait_until="load", timeout=self.timeout)
        html = await self._page.content()
        try:
            import trafilatura  # type: ignore[import-not-found]

            md = trafilatura.extract(
                html,
                output_format="markdown",
                include_tables=True,
                include_links=True,
                include_images=False,
                no_fallback=False,
            ) or ""
        except ImportError:
            logger.warning("trafilatura not installed; falling back to innerText")
            md = await self._page.evaluate("() => document.body ? document.body.innerText : ''")
        if not md.strip():
            md = "(no readable content extracted)"
        if len(md) > _MAX_CONTENT_CHARS:
            md = md[:_MAX_CONTENT_CHARS] + "\n\n...[truncated]"
        return md

    async def get_content_html(self, url: str) -> str:
        """Extract the raw HTML of the page after JS execution."""
        url = self._validate_url(url)
        await self._ensure_browser()
        assert self._page is not None
        await self._page.goto(url, wait_until="load", timeout=self.timeout)
        html = await self._page.content()
        if len(html) > _MAX_CONTENT_CHARS:
            html = html[:_MAX_CONTENT_CHARS] + "\n<!-- ...[truncated] -->"
        return html

    async def get_links(self, url: str) -> List[Dict[str, str]]:
        """Extract all ``<a href>`` links on the page.

        Returns a list of ``{"text": ..., "href": ...}`` dicts with
        absolute URLs (relative links are resolved against ``url``).
        Limited to :data:`_MAX_LINKS` entries.
        """
        url = self._validate_url(url)
        await self._ensure_browser()
        assert self._page is not None
        await self._page.goto(url, wait_until="load", timeout=self.timeout)
        raw_links = await self._page.evaluate(
            """() => {
                const anchors = Array.from(document.querySelectorAll('a[href]'));
                return anchors.map(a => ({
                    text: (a.textContent || '').trim().slice(0, 200),
                    href: a.href,
                }));
            }"""
        )
        base = url
        out: List[Dict[str, str]] = []
        seen = set()
        for entry in raw_links or []:
            href = (entry.get("href") or "").strip()
            if not href:
                continue
            # Resolve relative URLs against the page base.
            absolute = urljoin(base, href)
            # Filter out non-http(s) (javascript:, mailto:, etc.).
            if urlparse(absolute).scheme not in ("http", "https"):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)
            out.append({"text": (entry.get("text") or "").strip(), "href": absolute})
            if len(out) >= _MAX_LINKS:
                break
        return out

    async def form_submit(self, selector: str = "") -> Dict[str, Any]:
        """Submit a form.

        If ``selector`` is given, the matching ``<form>`` is submitted.
        Otherwise the first ``<form>`` on the page is submitted.
        """
        await self._ensure_browser()
        assert self._page is not None
        if selector:
            await self._page.evaluate(
                "(sel) => { const f = document.querySelector(sel); if (f && f.submit) f.submit(); }",
                selector,
            )
            used_selector = selector
        else:
            await self._page.evaluate(
                "() => { const f = document.querySelector('form'); if (f && f.submit) f.submit(); }"
            )
            used_selector = "form"
        # Wait briefly for navigation to begin.
        try:
            await self._page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception as exc:  # noqa: BLE001 — non-fatal
            logger.debug("networkidle wait failed after form submit: %s", exc)
        title = await self._page.title()
        current_url = self._page.url
        logger.info("submitted form via %s — now at %s", used_selector, current_url)
        return self._ok(
            output=f"Submitted form ({used_selector}); now at {current_url} — title: {title}",
            extra={"selector": used_selector, "url": current_url, "title": title},
        )

    # ── VLM integration ───────────────────────────────────────────────
    async def analyze_screenshot_with_vlm(
        self,
        screenshot: bytes,
        prompt: str = "Describe this web page screenshot. Focus on security-relevant elements: login forms, error messages, exposed tokens, debug info, or anything that looks suspicious.",
    ) -> str:
        """Analyze a screenshot with a Vision-Language Model.

        Uses the SecurAgentX provider registry to dispatch to whichever
        vision-capable provider is configured (OpenAI, Gemini, Anthropic,
        Bedrock). The screenshot is sent as a base64-encoded PNG.

        Returns the model's textual description. Raises ``RuntimeError``
        if no vision-capable provider is available.
        """
        if not screenshot:
            return "(empty screenshot)"

        # Lazy import — keeps the module importable when providers are absent.
        try:
            from securagentx.providers.base import ProviderType
            from securagentx.providers.registry import ProviderRegistry
        except ImportError as exc:
            raise RuntimeError(
                "securagentx.providers not available — cannot invoke VLM"
            ) from exc

        registry = ProviderRegistry()
        # Pick the first vision-capable provider with creds in the env.
        vision_order = [
            ProviderType.OPENAI, ProviderType.GEMINI, ProviderType.ANTHROPIC,
            ProviderType.BEDROCK, ProviderType.GLM, ProviderType.QWEN,
            ProviderType.KIMI, ProviderType.DEEPSEEK,
        ]
        available = set(registry.list_available_providers())  # type: ignore[attr-defined]
        chosen: Optional[ProviderType] = next(
            (p for p in vision_order if p in available), None
        )
        if chosen is None:
            raise RuntimeError(
                "no vision-capable LLM provider configured — "
                "set OPENAI_API_KEY / GEMINI_API_KEY / ANTHROPIC_API_KEY "
                "to enable screenshot analysis"
            )

        provider = registry.create(chosen)  # type: ignore[attr-defined]
        b64 = base64.b64encode(screenshot).decode("ascii")
        data_url = f"data:image/png;base64,{b64}"

        # Build a multimodal message. We use the OpenAI-style payload and
        # let the provider adapter translate. The base Provider interface
        # may not natively support images, so we wrap in a try/except to
        # surface a clear error.
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ],
            }
        ]
        try:
            # Providers expose a generate() method; the exact signature
            # varies so we attempt the most common shape.
            response = await asyncio.to_thread(
                provider.generate, messages, max_tokens=1000  # type: ignore[arg-type]
            )
        except TypeError:
            # Fallback: providers may expose chat() instead.
            response = await asyncio.to_thread(
                getattr(provider, "chat"), messages  # type: ignore[arg-type]
            )

        # Normalise various response shapes to plain text.
        if isinstance(response, str):
            return response
        if isinstance(response, dict):
            return (
                response.get("content")
                or response.get("text")
                or response.get("output")
                or str(response)
            )
        return str(response)

    # ── Cleanup ───────────────────────────────────────────────────────
    async def close(self) -> None:
        """Tear down the page, context, browser, and Playwright driver."""
        if self._closed:
            return
        self._closed = True
        errors: List[str] = []
        for resource, name in (
            (self._page, "page"),
            (self._context, "context"),
            (self._browser, "browser"),
        ):
            if resource is None:
                continue
            try:
                await resource.close()
            except Exception as exc:  # noqa: BLE001 — best-effort cleanup
                errors.append(f"{name}: {exc}")
                logger.debug("error closing %s: %s", name, exc)
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as exc:  # noqa: BLE001 — best-effort cleanup
                errors.append(f"playwright: {exc}")
                logger.debug("error stopping playwright: %s", exc)
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None
        if errors:
            logger.warning("browser close completed with %d error(s): %s", len(errors), errors)

    # ── Async context manager protocol ────────────────────────────────
    async def __aenter__(self) -> "BrowserTool":
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:  # type: ignore[no-untyped-def]
        await self.close()

    # ── Helpers ───────────────────────────────────────────────────────
    @staticmethod
    def _ok(output: str, screenshot: Optional[bytes] = None,
            extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Build a success dict, encoding any screenshot as base64."""
        result: Dict[str, Any] = {
            "success": True,
            "output": output,
            "screenshot": (
                base64.b64encode(screenshot).decode("ascii")
                if screenshot else None
            ),
        }
        if extra:
            result.update(extra)
        return result


__all__ = ["BrowserAction", "BrowserTool", "INSECURE", "DEFAULT_TIMEOUT_MS"]
