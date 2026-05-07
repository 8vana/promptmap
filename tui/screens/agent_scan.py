import asyncio
import logging

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label
from textual.containers import Container, Horizontal

from engine.context import AttackContext
from engine.events import (
    EVT_AGENT_ACTION, EVT_AGENT_DONE, EVT_COMPLETE, EVT_ERROR,
    EVT_INFO, EVT_PROMPT, EVT_RESPONSE, EVT_SCORE,
    ProgressEvent,
)
from tui.widgets.activity_log import ActivityLog
from tui.widgets.screen_log_handler import ScreenLogHandler
from tui.widgets.smart_rich_log import SmartScrollRichLog


class AgentScanScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    class Progress(Message):
        def __init__(self, event: ProgressEvent) -> None:
            super().__init__()
            self.event = event

    def __init__(self) -> None:
        super().__init__()
        self._log_handler: ScreenLogHandler | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="agent-form"):
            yield Label("Agent Scan", classes="panel-title")
            yield Label("Objective", classes="field-label")
            yield Input(
                placeholder="Describe the attack objective for the agent to pursue...",
                id="objective-input",
            )
            with Horizontal():
                yield Button("Start", id="btn-start", variant="primary")
                yield Button("Back",  id="btn-back")
            yield Label("", id="status-label")
        yield SmartScrollRichLog(id="agent-log")
        yield ActivityLog(id="agent-activity-log")
        yield Footer()

    def on_mount(self) -> None:
        self._log_handler = ScreenLogHandler(self.app, self._on_log_record)
        logging.getLogger("promptmap").addHandler(self._log_handler)

    def on_unmount(self) -> None:
        if self._log_handler is not None:
            logging.getLogger("promptmap").removeHandler(self._log_handler)
            self._log_handler = None

    def _on_log_record(self, record: logging.LogRecord) -> None:
        try:
            self.query_one("#agent-activity-log", ActivityLog).add_record(record)
        except Exception:
            pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self._start_agent()
        elif event.button.id == "btn-back":
            self.app.pop_screen()

    def _start_agent(self) -> None:
        objective = self.query_one("#objective-input", Input).value.strip()
        if not objective:
            self.notify("Please enter an objective.", severity="warning")
            return
        if not self.app.settings_ready():
            self.notify(
                "Settings incomplete — check API endpoint, LLM names, and API keys.",
                severity="error",
            )
            return
        try:
            ctx = self.app.build_context()
        except FileNotFoundError as exc:
            self.notify(
                f"Browser config file not found:\n{exc.filename or exc}",
                title="Cannot start agent",
                severity="error",
                timeout=8,
            )
            return
        except Exception as exc:
            self.notify(
                f"Failed to initialize target: {exc}",
                title="Cannot start agent",
                severity="error",
                timeout=8,
            )
            return
        self.query_one("#btn-start", Button).disabled = True
        self.run_worker(self._agent_worker(ctx, objective), exclusive=True)

    async def _agent_worker(self, ctx: AttackContext, objective: str) -> None:
        from attacks.agent.attack_agent import AttackAgent
        from engine.logging_setup import get_logger
        _wlog = get_logger("tui.agent_scan")
        _wlog.info("agent worker: started (lang=%s, target_type=%s)",
                   ctx.language, type(ctx.target).__name__)

        agent = AttackAgent()
        queue = ctx.progress_queue
        done_event = asyncio.Event()

        async def drain() -> None:
            while not done_event.is_set():
                while not queue.empty():
                    self.post_message(self.Progress(queue.get_nowait()))
                await asyncio.sleep(0.02)
            while not queue.empty():
                self.post_message(self.Progress(queue.get_nowait()))

        drain_task = asyncio.create_task(drain())
        _wlog.info("agent worker: drain task scheduled, calling agent.run()")
        try:
            # AttackAgent.run() returns a list, and saves each AttackResult to
            # ctx.memory itself as it goes — no need to re-save here.
            await agent.run(ctx, objective)
            _wlog.info("agent worker: agent.run() returned normally")
        except Exception as exc:
            _wlog.exception("agent worker: agent.run() raised")
            self.post_message(self.Progress(
                ProgressEvent(type=EVT_ERROR, data={"text": str(exc)})
            ))
        finally:
            _wlog.info("agent worker: tearing down")
            done_event.set()
            await drain_task
            # Playwright のブラウザプロセス等は asyncio loop が閉じる前に
            # 解放しておかないと、終了時に "Event loop is closed" 警告が出る。
            await ctx.close_all_targets()
            _wlog.info("agent worker: teardown complete")

        self.query_one("#btn-start", Button).disabled = False

    def on_agent_scan_screen_progress(self, message: "AgentScanScreen.Progress") -> None:
        evt = message.event
        log = self.query_one("#agent-log", SmartScrollRichLog)
        status = self.query_one("#status-label", Label)

        if evt.type == EVT_AGENT_ACTION:
            t = Text()
            t.append("[Agent] → ", style="bold cyan")
            t.append(evt.data.get("attack", ""), style="cyan")
            ptech = evt.data.get("prompt_technique") or ""
            if ptech:
                t.append(f" [{ptech}]", style="bold magenta")
            t.append(f"  {evt.data.get('objective', '')[:80]}", style="dim")
            log.write(t)
        elif evt.type == EVT_INFO:
            t = Text()
            t.append(str(evt.data.get("text", "")), style="dim cyan")
            log.write(t)
        elif evt.type == EVT_PROMPT:
            t = Text()
            t.append(f"T{evt.turn:02d} → ", style="bold cyan")
            t.append(str(evt.data.get("text", ""))[:100], style="cyan")
            log.write(t)
        elif evt.type == EVT_RESPONSE:
            t = Text()
            t.append(f"T{evt.turn:02d} ← ", style="bold yellow")
            t.append(str(evt.data.get("text", ""))[:100], style="yellow")
            log.write(t)
        elif evt.type == EVT_SCORE:
            score = evt.data.get("score", 0.0)
            achieved = evt.data.get("achieved", False)
            t = Text()
            t.append(f"T{evt.turn:02d} score={score:.2f} ", style="bold")
            t.append("✓" if achieved else "✗", style="bold red" if achieved else "dim")
            log.write(t)
        elif evt.type == EVT_AGENT_DONE:
            t = Text()
            t.append("[Done] ", style="bold green")
            t.append(evt.data.get("summary", ""), style="green")
            log.write(t)
            status.update("Agent scan complete")
        elif evt.type == EVT_COMPLETE:
            achieved = evt.data.get("achieved", False)
            score = evt.data.get("score", 0.0)
            t = Text()
            t.append("✓ " if achieved else "✗ ", style="bold red" if achieved else "bold")
            t.append(f"Final score: {score:.2f}", style="dim")
            log.write(t)
        elif evt.type == EVT_ERROR:
            t = Text()
            t.append("[Error] ", style="bold red")
            t.append(evt.data.get("text", ""), style="red")
            log.write(t)
            status.update(f"Error: {evt.data.get('text', '')[:60]}")

    def action_go_back(self) -> None:
        self.app.pop_screen()
