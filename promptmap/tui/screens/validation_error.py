"""Blocking screen shown when dataset / config integrity checks fail at startup.

Displayed in place of the normal HomeScreen when ``validate_dataset_references``
returns errors. The user is forced to acknowledge and exit; PromptMap cannot
proceed because the wizard depends on the validated metadata.
"""

from __future__ import annotations

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Label, Static


class ValidationErrorScreen(Screen):
    BINDINGS = [
        Binding("enter", "exit_app", "Exit"),
        Binding("escape", "exit_app", "Exit"),
        Binding("q", "exit_app", "Exit"),
    ]

    def __init__(self, errors: list[str]) -> None:
        super().__init__()
        self._errors = errors

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="validation-dialog"):
            yield Label("Configuration error — PromptMap cannot start", classes="panel-title")
            yield Label(
                "The dataset / config files contain inconsistent references. "
                "Fix the items below and relaunch:",
                classes="field-label",
            )
            body = "\n".join(f"  • {e}" for e in self._errors) or "  (no details)"
            yield Static(body, id="validation-errors")
            with Horizontal(id="validation-buttons"):
                yield Button("Exit", id="btn-exit", variant="primary")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-exit":
            self.app.exit()

    def action_exit_app(self) -> None:
        self.app.exit()
