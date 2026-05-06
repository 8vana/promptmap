"""``logging.Handler`` that forwards selected records to a Textual screen.

Used by the Manual / Agent scan screens to surface main trial activities
(browser launch, navigation outcomes, LLM lifecycle, warnings/errors) in
real time without instrumenting engine code — every relevant signal is
already going through ``promptmap.*`` loggers.

Filtering is namespace-aware: each rule is a ``(prefix, min_level)`` tuple,
the longest matching prefix wins. The default rules are tuned so that
``DEBUG`` step traces stay out of the live panel (read those via the
full Logs viewer with ``l``) while INFO+ lifecycle messages and any
WARNING+ from any logger surface immediately.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Callable


# Default per-namespace minimum level. Longer prefixes win after sorting.
DEFAULT_RULES: list[tuple[str, int]] = [
    # In-page browser events (console / pageerror / requestfailed):
    # noisy by nature → only surface warnings/errors.
    ("promptmap.targets.playwright.browser", logging.WARNING),
    # Browser operations: launch / ready / close at INFO, plus FAILED / TIMEOUT
    # at WARNING — DEBUG step start/OK lines stay in the file log.
    ("promptmap.targets.playwright",         logging.INFO),
    # LLM target lifecycle (close, send FAILED).
    ("promptmap.targets",                    logging.INFO),
    # Catch-all safety net: anything WARNING+ from any logger surfaces.
    ("",                                     logging.WARNING),
]


class ScreenLogHandler(logging.Handler):
    """Forward filtered ``promptmap.*`` log records to a Textual callback."""

    def __init__(
        self,
        app,                                                 # textual.app.App
        callback: Callable[[logging.LogRecord], None],
        rules: list[tuple[str, int]] | None = None,
    ) -> None:
        # Accept everything; per-namespace filtering happens in emit().
        super().__init__(level=logging.DEBUG)
        self._app = app
        self._callback = callback
        # Sort specific → general so the first matching prefix wins.
        self._rules = sorted(
            rules if rules is not None else DEFAULT_RULES,
            key=lambda r: len(r[0]),
            reverse=True,
        )

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.levelno < self._min_level_for(record.name):
                return
            # Always defer the callback to the app's event-loop thread:
            #   - Same thread (asyncio coroutines like Playwright steps or the
            #     attack worker): schedule on the running loop. Calling
            #     `app.call_from_thread` here would raise RuntimeError because
            #     Textual rejects same-thread invocations.
            #   - Different thread (rare; e.g. a future worker that spins its
            #     own thread): hop via `app.call_from_thread`.
            try:
                loop = asyncio.get_running_loop()
                loop.call_soon(self._callback, record)
                return
            except RuntimeError:
                # No running loop on this thread — fall through to the
                # cross-thread path.
                pass
            try:
                self._app.call_from_thread(self._callback, record)
            except RuntimeError:
                # App has stopped or thread mismatch — drop the record.
                pass
        except Exception:
            self.handleError(record)

    def _min_level_for(self, logger_name: str) -> int:
        for prefix, level in self._rules:
            if not prefix:
                return level
            if logger_name == prefix or logger_name.startswith(prefix + "."):
                return level
        return logging.WARNING
