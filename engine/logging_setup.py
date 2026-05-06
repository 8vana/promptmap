"""Application-wide logging configuration.

Two log streams handled here:

* **Operational log** (`promptmap.*` namespace) — written via Python `logging`
  to ``~/.promptmap/logs/promptmap.log`` with rotation. Covers errors, warnings,
  and lifecycle messages from adapters / TUI screens / settings loading.

* **Debug toggle** — controlled by the env var ``PROMPTMAP_LOG_LEVEL`` (default
  ``INFO``). Setting ``PROMPTMAP_LOG_LEVEL=DEBUG`` switches the file handler
  (and the per-module loggers) to DEBUG, capturing per-LLM-call traces and
  internal state transitions.

Conversation telemetry (per-LLM-call request/response payloads, latencies,
token usage) is handled separately by ``engine.conversation_log`` and written
to ``~/.promptmap/runs/<timestamp>.jsonl`` in an OTEL-leaning flat format.
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

_LOG_DIR = Path(os.path.expanduser("~/.promptmap/logs"))
_LOG_FILE = _LOG_DIR / "promptmap.log"
_MAX_BYTES = 10 * 1024 * 1024  # 10 MB
_BACKUP_COUNT = 5

_initialised = False


def setup_logging(level: str | int | None = None) -> Path:
    """Configure the ``promptmap`` logger namespace. Idempotent.

    Args:
        level: Optional explicit log level (e.g. ``"DEBUG"`` or ``logging.DEBUG``).
            If not given, ``PROMPTMAP_LOG_LEVEL`` env var is consulted; the
            default is ``INFO``.

    Returns:
        The absolute path of the log file in use.
    """
    global _initialised

    resolved_level = _resolve_level(level)

    root = logging.getLogger("promptmap")
    if _initialised:
        # 既に初期化済みでも、レベルだけは再設定できるようにしておく。
        root.setLevel(resolved_level)
        for h in root.handlers:
            h.setLevel(resolved_level)
        return _LOG_FILE

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)-7s %(name)s :: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.handlers.RotatingFileHandler(
        _LOG_FILE,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(resolved_level)

    root.setLevel(resolved_level)
    root.addHandler(file_handler)
    # ルートロガーへの伝播は止める（TUI が標準出力を握っているので、stdout に
    # ログを流すと画面が汚れる）。
    root.propagate = False

    _install_unraisable_filter()

    _initialised = True
    root.info(
        "Logging initialised at level=%s file=%s",
        logging.getLevelName(resolved_level), _LOG_FILE,
    )
    return _LOG_FILE


def _install_unraisable_filter() -> None:
    """Silence the well-known asyncio "Event loop is closed" noise on shutdown.

    When Playwright (or any asyncio-subprocess user) hands a transport to the
    GC and the GC runs *after* the loop is torn down, ``BaseSubprocessTransport
    .__del__`` tries to schedule cleanup on the dead loop and a ``RuntimeError:
    Event loop is closed`` is reported via :func:`sys.unraisablehook`. The
    error is purely cosmetic — by the time it fires, the process is already
    exiting — so we redirect it to the application log instead of stderr.
    Any *other* unraisable error still surfaces normally.
    """
    log = get_logger("asyncio")
    prev_hook = sys.unraisablehook

    def _hook(unraisable):  # type: ignore[no-untyped-def]
        exc = unraisable.exc_value
        is_known_noise = (
            isinstance(exc, RuntimeError)
            and "Event loop is closed" in str(exc)
            and "BaseSubprocessTransport" in repr(unraisable.object)
        )
        if is_known_noise:
            log.debug("Suppressed asyncio shutdown noise: %s", exc)
            return
        prev_hook(unraisable)

    sys.unraisablehook = _hook


def get_logger(name: str) -> logging.Logger:
    """Return a child logger under ``promptmap.``.

    Use ``get_logger(__name__)`` from each module so the logger name reflects
    the source location, while still inheriting the configured handler.
    """
    if not name.startswith("promptmap"):
        name = f"promptmap.{name}"
    return logging.getLogger(name)


def _resolve_level(explicit: str | int | None) -> int:
    if explicit is not None:
        return logging.getLevelName(explicit) if isinstance(explicit, str) else explicit
    env = os.getenv("PROMPTMAP_LOG_LEVEL", "").strip().upper()
    if env in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        return logging.getLevelName(env)
    return logging.INFO
