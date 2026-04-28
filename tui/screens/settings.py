from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label
from textual.containers import Container, Horizontal

_FIELDS = [
    ("api_endpoint",   "Target API Endpoint",           "http://localhost:8000/chat"),
    ("body_template",  "Request Body Template",         '{"text": "{PROMPT}"}'),
    ("response_key",   "Response JSON Key",             "text"),
    ("adv_llm_name",   "Adversarial LLM  (e.g. gpt-4o-mini)", "gpt-4o-mini"),
    ("score_llm_name", "Score LLM  (e.g. gpt-4o-mini)", "gpt-4o-mini"),
]


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(classes="settings-form"):
            yield Label("⚙  Settings", classes="panel-title")
            for field_id, label_text, placeholder in _FIELDS:
                yield Label(label_text, classes="field-label")
                yield Input(placeholder=placeholder, id=field_id)
            yield Label(
                "API keys are read from ADV_LLM_API_KEY / SCORE_LLM_API_KEY env vars.",
                classes="field-label",
            )
            with Horizontal():
                yield Button("Save",   id="btn-save",   variant="primary")
                yield Button("Cancel", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        s = self.app.settings
        for field_id, *_ in _FIELDS:
            widget = self.query_one(f"#{field_id}", Input)
            widget.value = s.get(field_id, "")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            updates = {fid: self.query_one(f"#{fid}", Input).value for fid, *_ in _FIELDS}
            self.app.update_settings(updates)
            self.notify("Settings saved.", title="Saved", severity="information")
            self.app.pop_screen()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()
