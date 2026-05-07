import asyncio
import logging
from dataclasses import dataclass

from textual.app import ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label
from textual.containers import Horizontal, Vertical

from engine.context import AttackContext
from engine.events import (
    EVT_INFO, EVT_PROMPT, EVT_RESPONSE, EVT_SCORE,
    EVT_BACKTRACK, EVT_ACHIEVED, EVT_COMPLETE, EVT_ERROR,
    ProgressEvent,
)
from tui.widgets.activity_log import ActivityLog
from tui.widgets.conversation_log import ConversationLog
from tui.widgets.score_panel import ScorePanel
from tui.widgets.screen_log_handler import ScreenLogHandler
from tui.widgets.smart_rich_log import SmartScrollRichLog


@dataclass
class ExecutionJob:
    """One (attack × prompt) pair to run."""
    attack_id: str
    objective: str
    technique_id: str = ""        # MITRE ATLAS technique ID
    prompt_technique: str = ""    # Prompt-crafting technique (config/prompt_techniques.yaml key)


class ExecutionScreen(Screen):
    BINDINGS = [
        Binding("escape", "go_back",   "Back"),
        Binding("l",      "open_logs", "Logs"),
    ]

    class Progress(Message):
        def __init__(self, event: ProgressEvent) -> None:
            super().__init__()
            self.event = event

    def __init__(self, ctx: AttackContext, jobs: list[ExecutionJob]) -> None:
        super().__init__()
        self._ctx = ctx
        self._jobs = jobs
        self._log_handler: ScreenLogHandler | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("", id="lbl-attack")
        yield Label("", id="lbl-objective")
        with Horizontal(id="exec-body"):
            with Vertical(id="exec-left"):
                yield ConversationLog(id="conv-log")
                yield ActivityLog(id="activity-log-exec")
            with Vertical(id="exec-right"):
                yield Label("Score History", id="scores-title")
                yield ScorePanel(id="score-log")
        yield Label("Running…", id="lbl-progress")
        with Horizontal(id="exec-bottom"):
            yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self._log_handler = ScreenLogHandler(self.app, self._on_log_record)
        logging.getLogger("promptmap").addHandler(self._log_handler)
        self._update_job_header(0)
        self.run_worker(self._batch_worker(), exclusive=True)

    def on_unmount(self) -> None:
        if self._log_handler is not None:
            logging.getLogger("promptmap").removeHandler(self._log_handler)
            self._log_handler = None

    def _on_log_record(self, record: logging.LogRecord) -> None:
        try:
            self.query_one("#activity-log-exec", ActivityLog).add_record(record)
        except Exception:
            # Screen may be unmounting between the handler firing and the
            # callback running on the app thread — drop the record silently.
            pass

    # ------------------------------------------------------------------ #
    #  Header / progress label updates                                     #
    # ------------------------------------------------------------------ #

    def _update_job_header(self, idx: int) -> None:
        if not self._jobs or idx >= len(self._jobs):
            return
        job = self._jobs[idx]
        total = len(self._jobs)
        self.query_one("#lbl-attack", Label).update(
            f"  [{idx + 1}/{total}] {job.attack_id}"
        )
        self.query_one("#lbl-objective", Label).update(
            f"  {job.objective[:90]}"
        )

    # ------------------------------------------------------------------ #
    #  Worker                                                              #
    # ------------------------------------------------------------------ #

    async def _batch_worker(self) -> None:
        queue = self._ctx.progress_queue
        all_done = asyncio.Event()

        async def drain() -> None:
            while not all_done.is_set():
                while not queue.empty():
                    self.post_message(self.Progress(queue.get_nowait()))
                await asyncio.sleep(0.02)
            while not queue.empty():
                self.post_message(self.Progress(queue.get_nowait()))

        drain_task = asyncio.create_task(drain())
        achieved_count = 0

        try:
            for idx, job in enumerate(self._jobs):
                # Worker runs on the app's event loop thread, so update widgets
                # directly. `call_from_thread` is only for true off-thread callers.
                self._update_job_header(idx)
                attack = self._ctx.available_attacks.get(job.attack_id)
                if attack is None:
                    self.post_message(self.Progress(ProgressEvent(
                        type=EVT_ERROR,
                        data={"text": f"Unknown attack: {job.attack_id}"},
                    )))
                    continue

                self.post_message(self.Progress(ProgressEvent(
                    type=EVT_INFO,
                    data={"text": (
                        f"── Job {idx + 1}/{len(self._jobs)}: {job.attack_id} "
                        f"— {job.objective[:80]}"
                    )},
                )))

                try:
                    result = await attack.run(
                        self._ctx,
                        job.objective,
                        prompt_technique=job.prompt_technique,
                    )
                    if job.technique_id:
                        result.atlas_techniques = [job.technique_id]
                    if job.prompt_technique:
                        result.metadata.setdefault("prompt_technique", job.prompt_technique)
                    self._ctx.memory.save_result(result)
                    if result.achieved:
                        achieved_count += 1
                except Exception as exc:
                    self.post_message(self.Progress(ProgressEvent(
                        type=EVT_ERROR,
                        data={"text": f"{job.attack_id}: {exc}"},
                    )))
        finally:
            self.post_message(self.Progress(ProgressEvent(
                type=EVT_INFO,
                data={"text": (
                    f"=== All jobs complete: {achieved_count}/{len(self._jobs)} achieved ==="
                )},
            )))
            all_done.set()
            await drain_task
            # Playwright のブラウザプロセス等は asyncio loop が閉じる前に
            # 解放しておかないと、終了時に "Event loop is closed" 警告が出る。
            await self._ctx.close_all_targets()

    # ------------------------------------------------------------------ #
    #  Progress event rendering                                            #
    # ------------------------------------------------------------------ #

    def on_execution_screen_progress(self, message: "ExecutionScreen.Progress") -> None:
        evt = message.event
        conv = self.query_one("#conv-log", ConversationLog)
        score_panel = self.query_one("#score-log", ScorePanel)
        status = self.query_one("#lbl-progress", Label)

        if evt.type == EVT_INFO:
            conv.add_info(evt.data.get("text", ""))
        elif evt.type == EVT_PROMPT:
            conv.add_user(evt.data.get("text", ""))
        elif evt.type == EVT_RESPONSE:
            conv.add_assistant(evt.data.get("text", ""))
        elif evt.type == EVT_SCORE:
            score_panel.add_score(
                evt.turn,
                evt.data.get("score", 0.0),
                evt.data.get("achieved", False),
                evt.data.get("rationale", ""),
            )
        elif evt.type == EVT_BACKTRACK:
            conv.add_info(f"↩ Backtrack {evt.data.get('count')}/{evt.data.get('max')}")
        elif evt.type == EVT_ACHIEVED:
            status.update("✓ Objective achieved!")
        elif evt.type == EVT_COMPLETE:
            achieved = evt.data.get("achieved", False)
            final_score = evt.data.get("score", 0.0)
            mark = "✓ Achieved" if achieved else "✗ Not achieved"
            status.update(f"Complete — {mark}  |  Score: {final_score:.2f}")
            conv.add_separator("Complete")
        elif evt.type == EVT_ERROR:
            status.update(f"Error: {evt.data.get('text', '')}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-back":
            self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()

    def action_open_logs(self) -> None:
        from tui.screens.log_viewer import LogViewerScreen
        self.app.push_screen(LogViewerScreen())
