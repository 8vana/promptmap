from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

from engine.base_target import TargetAdapter
from engine.logging_setup import get_logger

if TYPE_CHECKING:
    from playwright.async_api import (
        Browser, BrowserContext, ConsoleMessage, Page, Playwright, Request,
    )
    from targets.browser_config import BrowserTargetConfig, NavigationStep


_logger = get_logger("targets.playwright")
# In-page events (console / pageerror / requestfailed) get a separate child
# logger so the log viewer can filter them out independently of operational
# logs (browser launch, step progress, timeouts).
_browser_logger = get_logger("targets.playwright.browser")

# Map Playwright console message types onto Python logging levels.
_CONSOLE_LEVEL_MAP = {
    "error":   logging.ERROR,
    "warning": logging.WARNING,
    "info":    logging.INFO,
    "log":     logging.DEBUG,
    "debug":   logging.DEBUG,
    "trace":   logging.DEBUG,
}


class PlaywrightTargetAdapter(TargetAdapter):
    """
    Browser-based target adapter using Playwright.

    Navigates to a web application via configured steps, then sends prompts
    through the embedded chat UI and extracts the AI's response.

    Supports:
    - Cookie / session-based authentication (transparent — real browser)
    - JWT in localStorage / Authorization header managed by JS (transparent)
    - Manual header injection via set_extra_http_headers navigation step
    - Response patterns: synchronous HTTP and async polling / SSE / WebSocket
      (both are handled transparently via DOM observation)

    Usage:
        config = load_browser_config("browser_target.yaml")
        target = PlaywrightTargetAdapter(config)
        response = await target.send(prompt, conversation_id)
        await target.close()
    """

    def __init__(self, config: "BrowserTargetConfig") -> None:
        self._config = config
        self._playwright: "Playwright | None" = None
        self._browser: "Browser | None" = None
        self._context: "BrowserContext | None" = None
        self._page: "Page | None" = None

    # ------------------------------------------------------------------
    # TargetAdapter interface
    # ------------------------------------------------------------------

    async def send(self, prompt: str, conversation_id: str) -> str:
        page = await self._ensure_ready()
        cfg = self._config.chat

        existing_count = await page.locator(cfg.response_selector).count()
        _logger.debug(
            "send conv=%s existing_responses=%d wait_strategy=%s",
            conversation_id, existing_count, cfg.response_wait_strategy,
        )

        t0 = time.perf_counter()
        await page.fill(cfg.input_selector, prompt)
        if cfg.send_selector:
            await page.click(cfg.send_selector)
        else:
            await page.press(cfg.input_selector, "Enter")

        if cfg.response_wait_strategy == "new_element":
            await self._wait_new_element(
                page, cfg.response_selector, existing_count, cfg.response_timeout
            )
        else:
            await self._wait_content_stable(
                page, cfg.response_selector, cfg.response_timeout
            )

        locator = page.locator(cfg.response_selector)
        count = await locator.count()
        if count == 0:
            _logger.warning(
                "send conv=%s returned empty — no element matched %r",
                conversation_id, cfg.response_selector,
            )
            return ""
        text = (await locator.nth(count - 1).inner_text()).strip()
        duration_ms = int((time.perf_counter() - t0) * 1000)
        _logger.debug(
            "send OK conv=%s response_chars=%d duration_ms=%d",
            conversation_id, len(text), duration_ms,
        )
        return text

    def reset_conversation(self, conversation_id: str) -> None:
        # reset_selector のクリックは非同期操作のため、同期インターフェースから
        # 直接呼び出せない。完全なリセットが必要な場合は close() → 再初期化を使用。
        pass

    async def close(self) -> None:
        if self._context:
            try:
                await self._context.close()
            except Exception:
                _logger.exception("Failed to close browser context")
            self._context = None
        if self._browser:
            _logger.info("Closing browser kind=%s", self._config.browser)
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._browser = None
        self._playwright = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_ready(self) -> "Page":
        """Launch the browser and run navigation steps on the first call."""
        if self._page is not None:
            return self._page

        from playwright.async_api import async_playwright

        _logger.info(
            "Launching browser kind=%s headless=%s nav_steps=%d",
            self._config.browser, self._config.headless,
            len(self._config.navigation),
        )

        t0 = time.perf_counter()
        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._config.browser)
        self._browser = await launcher.launch(headless=self._config.headless)

        context_kwargs: dict = {}
        creds = self._config.http_credentials
        if creds is not None:
            context_kwargs["http_credentials"] = {
                "username": creds.username,
                "password": creds.password,
            }
            _logger.info(
                "Using HTTP credentials for context (username=%s)", creds.username,
            )
        self._context = await self._browser.new_context(**context_kwargs)
        self._page = await self._context.new_page()
        self._attach_browser_event_handlers(self._page)

        total = len(self._config.navigation)
        for i, step in enumerate(self._config.navigation, start=1):
            _logger.debug("nav step %d/%d", i, total)
            await self._run_step(self._page, step)

        duration_ms = int((time.perf_counter() - t0) * 1000)
        _logger.info(
            "Browser ready: %d nav step(s) completed in %d ms",
            total, duration_ms,
        )
        return self._page

    def _attach_browser_event_handlers(self, page: "Page") -> None:
        """Forward in-page console / error / network events to the log.

        These are best-effort observers — the handlers must not raise, since
        Playwright invokes them from its event loop and an exception would
        either be swallowed silently or crash the page lifecycle.
        """
        def _on_console(msg: "ConsoleMessage") -> None:
            try:
                level = _CONSOLE_LEVEL_MAP.get(msg.type, logging.DEBUG)
                loc = msg.location or {}
                where = f"{loc.get('url', '')}:{loc.get('lineNumber', '?')}"
                _browser_logger.log(
                    level, "[console.%s] %s (%s)", msg.type, msg.text, where,
                )
            except Exception:
                _browser_logger.exception("Failed to handle console event")

        def _on_pageerror(err: Exception) -> None:
            try:
                _browser_logger.error("[pageerror] %s", err)
            except Exception:
                _browser_logger.exception("Failed to handle pageerror event")

        def _on_requestfailed(request: "Request") -> None:
            try:
                failure = request.failure or "unknown"
                _browser_logger.warning(
                    "[requestfailed] %s %s — %s",
                    request.method, request.url, failure,
                )
            except Exception:
                _browser_logger.exception("Failed to handle requestfailed event")

        page.on("console", _on_console)
        page.on("pageerror", _on_pageerror)
        page.on("requestfailed", _on_requestfailed)

    async def _run_step(self, page: "Page", step: "NavigationStep") -> None:
        descriptor = self._describe_step(step)
        _logger.debug("step start %s", descriptor)
        t0 = time.perf_counter()
        try:
            if step.action == "goto":
                await page.goto(step.url, timeout=step.timeout)

            elif step.action == "fill":
                await page.fill(step.selector, step.value or "", timeout=step.timeout)

            elif step.action == "click":
                await page.click(step.selector, timeout=step.timeout)

            elif step.action == "wait_for_selector":
                await page.wait_for_selector(step.selector, timeout=step.timeout)

            elif step.action == "wait_for_url":
                await page.wait_for_url(step.pattern, timeout=step.timeout)

            elif step.action == "select":
                await page.select_option(step.selector, step.value or "", timeout=step.timeout)

            elif step.action == "press":
                await page.press(step.selector or "body", step.key or "Enter")

            elif step.action == "set_extra_http_headers":
                # Inject fixed HTTP headers (e.g. Authorization: Bearer <token>)
                await page.set_extra_http_headers(step.headers or {})

            elif step.action == "evaluate":
                # Execute arbitrary JavaScript (e.g. localStorage manipulation)
                await page.evaluate(step.expression or "")

        except Exception:
            duration_ms = int((time.perf_counter() - t0) * 1000)
            _logger.exception(
                "step FAILED %s duration_ms=%d", descriptor, duration_ms,
            )
            raise

        duration_ms = int((time.perf_counter() - t0) * 1000)
        _logger.debug("step OK %s duration_ms=%d", descriptor, duration_ms)

    @staticmethod
    def _describe_step(step: "NavigationStep") -> str:
        parts = [f"action={step.action}"]
        if step.url:
            parts.append(f"url={step.url}")
        if step.selector:
            parts.append(f"selector={step.selector!r}")
        if step.pattern:
            parts.append(f"pattern={step.pattern!r}")
        if step.key:
            parts.append(f"key={step.key!r}")
        if step.headers:
            parts.append(f"headers={list(step.headers.keys())}")
        return " ".join(parts)

    async def _wait_new_element(
        self, page: "Page", selector: str, initial_count: int, timeout_ms: int
    ) -> None:
        """Wait until a new DOM element matching *selector* appears."""
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if await page.locator(selector).count() > initial_count:
                return
            await asyncio.sleep(0.3)
        _logger.error(
            "wait_new_element TIMEOUT selector=%r initial=%d after=%dms",
            selector, initial_count, timeout_ms,
        )
        raise TimeoutError(
            f"No new response element appeared within {timeout_ms} ms "
            f"(selector: {selector!r})"
        )

    async def _wait_content_stable(
        self, page: "Page", selector: str, timeout_ms: int
    ) -> None:
        """Wait until the last matching element's text stops changing for 1.5 s.

        Suitable for streaming / typewriter UIs where the response is updated
        incrementally rather than appearing all at once.
        """
        deadline = time.monotonic() + timeout_ms / 1000
        prev_text = ""
        stable_ticks = 0

        while time.monotonic() < deadline:
            await asyncio.sleep(0.5)
            locator = page.locator(selector)
            count = await locator.count()
            if count == 0:
                continue
            current_text = (await locator.nth(count - 1).inner_text()).strip()
            if current_text and current_text == prev_text:
                stable_ticks += 1
                if stable_ticks >= 3:  # stable for 1.5 s
                    return
            else:
                stable_ticks = 0
                prev_text = current_text
        # Timeout reached — return whatever is present rather than raising.
        # Surface this via a WARNING so the silent fallback is observable.
        _logger.warning(
            "wait_content_stable TIMEOUT selector=%r last_chars=%d "
            "(returning current text)",
            selector, len(prev_text),
        )
