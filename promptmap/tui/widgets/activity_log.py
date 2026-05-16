"""Compact, level-coloured log line panel embedded in the Scan screens.

Renders one line per ``logging.LogRecord``:

    HH:MM:SS  LEVEL   short.logger.name   message

The ``promptmap.`` prefix is stripped from logger names so the line fits
in a narrow pane. Long messages wrap.
"""

from __future__ import annotations

import logging
import time

from rich.text import Text

from tui.widgets.smart_rich_log import SmartScrollRichLog


_LEVEL_STYLE = {
    "DEBUG":    "dim white",
    "INFO":     "white",
    "WARNING":  "bold yellow",
    "ERROR":    "bold red",
    "CRITICAL": "bold white on red",
}

# 5-wide aligned tag for each level.
_LEVEL_TAG = {
    "DEBUG":    "DEBUG",
    "INFO":     "INFO ",
    "WARNING":  "WARN ",
    "ERROR":    "ERROR",
    "CRITICAL": "CRIT ",
}


class ActivityLog(SmartScrollRichLog):
    """Live operational activity readout for a Scan screen."""

    def __init__(self, **kwargs) -> None:
        kwargs.setdefault("auto_scroll", True)
        kwargs.setdefault("markup", False)
        kwargs.setdefault("wrap", True)
        super().__init__(**kwargs)

    def add_record(self, record: logging.LogRecord) -> None:
        ts = time.strftime("%H:%M:%S", time.localtime(record.created))
        level = record.levelname
        name = record.name
        if name.startswith("promptmap."):
            name = name[len("promptmap."):]
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)

        line = Text()
        line.append(ts, style="dim cyan")
        line.append(f"  {_LEVEL_TAG.get(level, level[:5]):<5}",
                    style=_LEVEL_STYLE.get(level, "white"))
        line.append(f"  {name}", style="dim #9999cc")
        line.append(f"  {msg}", style="white")
        self.write(line)
