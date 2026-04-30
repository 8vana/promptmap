from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

from engine.base_target import TargetAdapter

if TYPE_CHECKING:
    from playwright.async_api import Browser, Page, Playwright
    from targets.browser_config import BrowserTargetConfig, NavigationStep


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
        self._page: "Page | None" = None

    # ------------------------------------------------------------------
    # TargetAdapter interface
    # ------------------------------------------------------------------

    async def send(self, prompt: str, conversation_id: str) -> str:
        page = await self._ensure_ready()
        cfg = self._config.chat

        existing_count = await page.locator(cfg.response_selector).count()

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
            return ""
        return (await locator.nth(count - 1).inner_text()).strip()

    def reset_conversation(self, conversation_id: str) -> None:
        # reset_selector のクリックは非同期操作のため、同期インターフェースから
        # 直接呼び出せない。完全なリセットが必要な場合は close() → 再初期化を使用。
        pass

    async def close(self) -> None:
        if self._browser:
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

        self._playwright = await async_playwright().start()
        launcher = getattr(self._playwright, self._config.browser)
        self._browser = await launcher.launch(headless=self._config.headless)
        self._page = await self._browser.new_page()

        for step in self._config.navigation:
            await self._run_step(self._page, step)

        return self._page

    async def _run_step(self, page: "Page", step: "NavigationStep") -> None:
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

    async def _wait_new_element(
        self, page: "Page", selector: str, initial_count: int, timeout_ms: int
    ) -> None:
        """Wait until a new DOM element matching *selector* appears."""
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            if await page.locator(selector).count() > initial_count:
                return
            await asyncio.sleep(0.3)
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
        # Timeout reached — return whatever is present rather than raising
