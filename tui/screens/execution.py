import asyncio

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
from tui.widgets.conversation_log import ConversationLog
from tui.widgets.score_panel import ScorePanel


class ExecutionScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    class Progress(Message):
        def __init__(self, event: ProgressEvent) -> None:
            super().__init__()
            self.event = event

    def __init__(self, ctx: AttackContext, attack_id: str, objective: str) -> None:
        super().__init__()
        self._ctx = ctx
        self._attack_id = attack_id
        self._objective = objective

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label(f"  {self._attack_id}", id="lbl-attack")
        yield Label(f"  {self._objective[:90]}", id="lbl-objective")
        with Horizontal(id="exec-body"):
            with Vertical(id="exec-left"):
                yield ConversationLog(id="conv-log")
            with Vertical(id="exec-right"):
                yield Label("Score History", id="scores-title")
                yield ScorePanel(id="score-log")
        yield Label("Running…", id="lbl-progress")
        with Horizontal():
            yield Button("Back", id="btn-back")
        yield Footer()

    def on_mount(self) -> None:
        self.run_worker(self._attack_worker(), exclusive=True)

    async def _attack_worker(self) -> None:
        attack = self._ctx.available_attacks.get(self._attack_id)
        if attack is None:
            self.post_message(self.Progress(
                ProgressEvent(type=EVT_ERROR, data={"text": f"Unknown attack: {self._attack_id}"})
            ))
            return

        queue = self._ctx.progress_queue
        attack_done = asyncio.Event()

        async def drain() -> None:
            while not attack_done.is_set():
                while not queue.empty():
                    self.post_message(self.Progress(queue.get_nowait()))
                await asyncio.sleep(0.02)
            while not queue.empty():
                self.post_message(self.Progress(queue.get_nowait()))

        drain_task = asyncio.create_task(drain())
        try:
            result = await attack.run(self._ctx, self._objective)
            self._ctx.memory.save_result(result)
        except Exception as exc:
            self.post_message(self.Progress(
                ProgressEvent(type=EVT_ERROR, data={"text": str(exc)})
            ))
        finally:
            attack_done.set()
            await drain_task

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
