from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RadioSet, RadioButton
from textual.containers import Container, Horizontal

_ATTACKS = [
    ("Single_PI_Attack",         "Single PI Attack  — direct injection, one turn"),
    ("Multi_Crescendo_Attack",   "Crescendo  — gradual escalation (multi-turn)"),
    ("Multi_PAIR_Attack",        "PAIR  — iterative refinement with attacker LLM"),
    ("Multi_Red_Teaming_Attack", "Red Teaming  — open-ended adversarial conversation"),
]


class ManualScanScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(classes="settings-form"):
            yield Label("Manual Scan", classes="panel-title")
            yield Label("Objective", classes="field-label")
            yield Input(
                placeholder="Describe what the attack should make the target do...",
                id="objective-input",
            )
            yield Label("Attack Method", classes="field-label")
            with RadioSet(id="attack-radio"):
                for attack_id, description in _ATTACKS:
                    yield RadioButton(description, id=attack_id)
            with Horizontal():
                yield Button("Start Scan", id="btn-start", variant="primary")
                yield Button("Cancel",     id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        buttons = list(self.query_one("#attack-radio", RadioSet).query(RadioButton))
        if buttons:
            buttons[0].value = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-start":
            self._start_scan()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()

    def _start_scan(self) -> None:
        objective = self.query_one("#objective-input", Input).value.strip()
        if not objective:
            self.notify("Please enter an objective.", severity="warning")
            return

        radio_set = self.query_one("#attack-radio", RadioSet)
        pressed = radio_set.pressed_button
        if pressed is None:
            self.notify("Please select an attack method.", severity="warning")
            return

        if not self.app.settings_ready():
            self.notify(
                "Settings incomplete — check API endpoint, LLM names, and API keys.",
                severity="error",
            )
            return

        ctx = self.app.build_context()
        from tui.screens.execution import ExecutionScreen
        self.app.push_screen(ExecutionScreen(ctx=ctx, attack_id=pressed.id, objective=objective))

    def action_go_back(self) -> None:
        self.app.pop_screen()
