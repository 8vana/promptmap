"""Live log viewer — tails the operational log and JSONL conversation log.

Two tabs:
    Operational   → ~/.promptmap/logs/promptmap.log (free-text, level filter)
    Conversation  → ~/.promptmap/runs/<run>.jsonl   (LLM call records, role filter)

Both panels poll the underlying file every 0.5 s and append new content
incrementally. If the file shrinks (rotation / truncation) the panel is
cleared and re-read from the start.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal
from textual.screen import Screen
from textual.widgets import (
    Button, Footer, Header, Label, Select, TabbedContent, TabPane,
)

from tui.widgets.smart_rich_log import SmartScrollRichLog


_LOG_FILE = Path(os.path.expanduser("~/.promptmap/logs/promptmap.log"))
_RUNS_DIR = Path(os.path.expanduser("~/.promptmap/runs"))

# Match the format set in engine.logging_setup:
#   "%(asctime)s %(levelname)-7s %(name)s :: %(message)s"
# datefmt: "%Y-%m-%d %H:%M:%S"
_LOG_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+"
    r"(?P<name>\S+)\s+::\s+"
    r"(?P<msg>.*)$"
)

_LEVEL_RANK = {
    "DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50,
}

_LEVEL_STYLE = {
    "DEBUG":    "dim white",
    "INFO":     "white",
    "WARNING":  "bold yellow",
    "ERROR":    "bold red",
    "CRITICAL": "bold white on red",
}

_ROLE_STYLE = {
    "target":      "yellow",
    "adversarial": "magenta",
    "scorer":      "cyan",
}


class LogViewerScreen(Screen):
    """Side-panel that tails the operational log and the per-run JSONL."""

    BINDINGS = [
        Binding("escape", "go_back", "Back"),
    ]

    def __init__(self) -> None:
        super().__init__()
        # Operational tail state
        self._op_pos: int = 0
        self._op_min_level: int = 0   # 0 = ALL
        # Conversation tail state
        self._conv_pos: int = 0
        self._conv_path: Path | None = None
        self._conv_role_filter: str = "all"
        self._poll_timer = None

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()

        with TabbedContent(id="log-tabs"):
            with TabPane("Operational", id="tab-op"):
                with Horizontal(id="op-toolbar", classes="log-toolbar"):
                    yield Label("Level:", classes="toolbar-label")
                    yield Select(
                        options=[
                            ("All",      "ALL"),
                            ("DEBUG",    "DEBUG"),
                            ("INFO",     "INFO"),
                            ("WARNING",  "WARNING"),
                            ("ERROR",    "ERROR"),
                        ],
                        value="ALL",
                        id="op-level",
                        allow_blank=False,
                    )
                    yield Button("Clear", id="op-clear", classes="toolbar-btn")
                yield SmartScrollRichLog(id="op-log", auto_scroll=True, markup=False, wrap=True)

            with TabPane("Conversation", id="tab-conv"):
                with Horizontal(id="conv-toolbar", classes="log-toolbar"):
                    yield Label("Run:", classes="toolbar-label")
                    yield Select(
                        options=self._list_runs(),
                        id="conv-file",
                        allow_blank=True,
                        prompt="(no runs)",
                    )
                    yield Label("Role:", classes="toolbar-label")
                    yield Select(
                        options=[
                            ("All",         "all"),
                            ("Target",      "target"),
                            ("Adversarial", "adversarial"),
                            ("Scorer",      "scorer"),
                        ],
                        value="all",
                        id="conv-role",
                        allow_blank=False,
                    )
                    yield Button("Clear", id="conv-clear", classes="toolbar-btn")
                yield SmartScrollRichLog(id="log-conv-log", auto_scroll=True, markup=False, wrap=True)

        yield Footer()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        # Default the conversation tab to the most recent run, if any.
        runs = self._list_runs()
        if runs:
            latest_path = runs[0][1]
            self._conv_path = Path(latest_path)
            try:
                self.query_one("#conv-file", Select).value = latest_path
            except Exception:
                pass

        self._reload_op()
        self._reload_conv()
        self._poll_timer = self.set_interval(0.5, self._poll)

    def on_unmount(self) -> None:
        if self._poll_timer is not None:
            self._poll_timer.stop()
            self._poll_timer = None

    # ------------------------------------------------------------------
    # Actions / events
    # ------------------------------------------------------------------

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "op-clear":
            self.query_one("#op-log", SmartScrollRichLog).clear()
        elif event.button.id == "conv-clear":
            self.query_one("#log-conv-log", SmartScrollRichLog).clear()

    def on_select_changed(self, event: Select.Changed) -> None:
        select_id = event.select.id
        value = event.value
        # Textual signals "no value" with Select.BLANK (sentinel object) — treat
        # it the same as not selecting anything.
        if value is Select.BLANK:
            return

        if select_id == "op-level":
            level = str(value)
            self._op_min_level = 0 if level == "ALL" else _LEVEL_RANK.get(level, 0)
            self._reload_op()
        elif select_id == "conv-role":
            self._conv_role_filter = str(value)
            self._reload_conv()
        elif select_id == "conv-file":
            self._conv_path = Path(str(value))
            self._reload_conv()

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    def _poll(self) -> None:
        self._tail_op()
        self._tail_conv()

    # -- operational ---------------------------------------------------

    def _reload_op(self) -> None:
        self.query_one("#op-log", SmartScrollRichLog).clear()
        self._op_pos = 0
        self._tail_op()

    def _tail_op(self) -> None:
        if not _LOG_FILE.exists():
            return
        rich = self.query_one("#op-log", SmartScrollRichLog)
        try:
            size = _LOG_FILE.stat().st_size
            if size < self._op_pos:
                # Rotated or truncated → start over.
                self._op_pos = 0
                rich.clear()
            with _LOG_FILE.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._op_pos)
                chunk = f.read()
                self._op_pos = f.tell()
        except OSError:
            return

        if not chunk:
            return
        for line in chunk.splitlines():
            self._render_op_line(rich, line)

    def _render_op_line(self, rich: SmartScrollRichLog, line: str) -> None:
        if not line:
            return
        m = _LOG_LINE_RE.match(line)
        if m is None:
            # Continuation line (traceback frame, etc.) — show as-is, dimmed.
            rich.write(Text(line, style="dim white"))
            return
        level = m.group("level")
        if _LEVEL_RANK[level] < self._op_min_level:
            return
        style = _LEVEL_STYLE.get(level, "white")
        t = Text()
        t.append(m.group("ts"), style="dim cyan")
        t.append(f"  {level:<7}", style=style)
        t.append(f"  {m.group('name')}", style="dim #9999cc")
        t.append(f"  {m.group('msg')}", style="white")
        rich.write(t)

    # -- conversation --------------------------------------------------

    def _reload_conv(self) -> None:
        self.query_one("#log-conv-log", SmartScrollRichLog).clear()
        self._conv_pos = 0
        self._tail_conv()

    def _tail_conv(self) -> None:
        if self._conv_path is None or not self._conv_path.exists():
            return
        rich = self.query_one("#log-conv-log", SmartScrollRichLog)
        try:
            size = self._conv_path.stat().st_size
            if size < self._conv_pos:
                self._conv_pos = 0
                rich.clear()
            with self._conv_path.open("r", encoding="utf-8", errors="replace") as f:
                f.seek(self._conv_pos)
                chunk = f.read()
                self._conv_pos = f.tell()
        except OSError:
            return

        if not chunk:
            return
        for line in chunk.splitlines():
            self._render_conv_line(rich, line)

    def _render_conv_line(self, rich: SmartScrollRichLog, line: str) -> None:
        if not line:
            return
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            rich.write(Text(f"[malformed JSONL] {line[:200]}", style="dim red"))
            return

        attrs = rec.get("attributes", {}) or {}
        role = attrs.get("promptmap.role", "?")
        if self._conv_role_filter != "all" and role != self._conv_role_filter:
            return

        status = rec.get("status", "?")
        system = attrs.get("gen_ai.system", "?")
        model = attrs.get("gen_ai.request.model", "?")
        duration_ms = rec.get("duration_ms", 0)
        start_time = rec.get("start_time", "")
        prompt = attrs.get("gen_ai.prompt", "") or ""
        completion = attrs.get("gen_ai.completion", "") or ""
        error = rec.get("error")

        role_style = _ROLE_STYLE.get(role, "white")

        head = Text()
        head.append(start_time, style="dim cyan")
        head.append(f"  [{role}]", style=role_style)
        head.append(f"  {system}/{model}", style="dim #9999cc")
        head.append(f"  ({duration_ms}ms)", style="dim white")
        head.append(f"  {status}", style="green" if status == "ok" else "bold red")
        rich.write(head)

        if prompt:
            t = Text()
            t.append("    → ", style="bold cyan")
            t.append(_truncate(prompt, 240), style="cyan")
            rich.write(t)
        if completion:
            t = Text()
            t.append("    ← ", style="bold yellow")
            t.append(_truncate(completion, 240), style="yellow")
            rich.write(t)
        if error:
            t = Text()
            t.append("    ✗ ", style="bold red")
            t.append(error, style="red")
            rich.write(t)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _list_runs() -> list[tuple[str, str]]:
        """Return [(label, path), ...] for the run files, newest first."""
        if not _RUNS_DIR.exists():
            return []
        files = sorted(_RUNS_DIR.glob("*.jsonl"), reverse=True)
        return [(f.name, str(f)) for f in files]


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "…"
