from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RadioSet, RadioButton
from textual.containers import Container, Horizontal

_HTTP_FIELDS = [
    ("api_endpoint",  "Target API Endpoint",           "http://localhost:8000/chat"),
    ("body_template", "Request Body Template",         '{"text": "{PROMPT}"}'),
    ("response_key",  "Response JSON Key",             "text"),
]

_BROWSER_FIELDS = [
    ("browser_config_path", "Browser Config Path (YAML)", "/path/to/browser_target.yaml"),
]

_LLM_FIELDS = [
    ("adv_llm_name",   "Adversarial LLM  (e.g. gpt-4o-mini)", "gpt-4o-mini"),
    ("score_llm_name", "Score LLM  (e.g. gpt-4o-mini)",        "gpt-4o-mini"),
]


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(classes="settings-form"):
            yield Label("⚙  Settings", classes="panel-title")

            # ── Target type ────────────────────────────────────────────
            yield Label("Target Type", classes="field-label")
            with RadioSet(id="target-type-radio"):
                yield RadioButton("HTTP API",     id="radio-http")
                yield RadioButton("Web Browser",  id="radio-browser")

            # ── HTTP config (visible when HTTP API is selected) ────────
            with Container(id="http-config"):
                for field_id, label_text, placeholder in _HTTP_FIELDS:
                    yield Label(label_text, classes="field-label")
                    yield Input(placeholder=placeholder, id=field_id)

            # ── Browser config (visible when Web Browser is selected) ──
            with Container(id="browser-config"):
                for field_id, label_text, placeholder in _BROWSER_FIELDS:
                    yield Label(label_text, classes="field-label")
                    yield Input(placeholder=placeholder, id=field_id)
                yield Label(
                    "Tip: use 'playwright codegen <url>' to record navigation steps.",
                    classes="field-label",
                )

            # ── LLM config (always visible) ────────────────────────────
            for field_id, label_text, placeholder in _LLM_FIELDS:
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
        target_type = s.get("target_type", "http")

        for field_id, *_ in _HTTP_FIELDS + _BROWSER_FIELDS + _LLM_FIELDS:
            widget = self.query_one(f"#{field_id}", Input)
            widget.value = s.get(field_id, "")

        self._apply_target_type(target_type)

        if target_type == "browser":
            self.query_one("#radio-browser", RadioButton).value = True
        else:
            self.query_one("#radio-http", RadioButton).value = True

    def _apply_target_type(self, target_type: str) -> None:
        http_cfg    = self.query_one("#http-config")
        browser_cfg = self.query_one("#browser-config")
        if target_type == "browser":
            http_cfg.display    = False
            browser_cfg.display = True
        else:
            http_cfg.display    = True
            browser_cfg.display = False

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        target_type = "browser" if event.index == 1 else "http"
        self._apply_target_type(target_type)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            is_browser = self.query_one("#radio-browser", RadioButton).value
            target_type = "browser" if is_browser else "http"

            updates = {"target_type": target_type}
            for fid, *_ in _HTTP_FIELDS + _BROWSER_FIELDS + _LLM_FIELDS:
                updates[fid] = self.query_one(f"#{fid}", Input).value

            self.app.update_settings(updates)
            self.notify("Settings saved.", title="Saved", severity="information")
            self.app.pop_screen()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()
