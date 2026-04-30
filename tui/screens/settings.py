from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RadioSet, RadioButton
from textual.containers import Container, Horizontal

from targets.factory import get_available_providers, get_missing_env_vars, PROVIDER_LABELS

_HTTP_FIELDS = [
    ("api_endpoint",  "Target API Endpoint",           "http://localhost:8000/chat"),
    ("body_template", "Request Body Template",         '{"text": "{PROMPT}"}'),
    ("response_key",  "Response JSON Key",             "text"),
]

_BROWSER_FIELDS = [
    ("browser_config_path", "Browser Config Path (YAML)", "/path/to/browser_target.yaml"),
]

_PROVIDERS = list(PROVIDER_LABELS.keys())  # ["openai", "anthropic", "gemini", "bedrock", "ollama"]


def _provider_label(provider: str, available: bool) -> str:
    label = PROVIDER_LABELS[provider]
    if available:
        return f"{label}"
    missing = get_missing_env_vars(provider)
    hint = " or ".join(missing) if provider == "gemini" else ", ".join(missing)
    return f"{label}  [requires: {hint}]"


class SettingsScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        availability = get_available_providers()

        yield Header()
        with Container(classes="settings-form"):
            yield Label("⚙  Settings", classes="panel-title")

            # ── Target type ────────────────────────────────────────────
            yield Label("Target Type", classes="field-label")
            with RadioSet(id="target-type-radio"):
                yield RadioButton("HTTP API",    id="radio-http")
                yield RadioButton("Web Browser", id="radio-browser")

            # ── HTTP config ────────────────────────────────────────────
            with Container(id="http-config"):
                for field_id, label_text, placeholder in _HTTP_FIELDS:
                    yield Label(label_text, classes="field-label")
                    yield Input(placeholder=placeholder, id=field_id)

            # ── Browser config ─────────────────────────────────────────
            with Container(id="browser-config"):
                for field_id, label_text, placeholder in _BROWSER_FIELDS:
                    yield Label(label_text, classes="field-label")
                    yield Input(placeholder=placeholder, id=field_id)
                yield Label(
                    "Tip: use 'playwright codegen <url>' to record navigation steps.",
                    classes="field-label",
                )

            # ── Adversarial LLM provider ───────────────────────────────
            yield Label("Adversarial LLM Provider", classes="field-label")
            with RadioSet(id="adv-provider-radio"):
                for p in _PROVIDERS:
                    avail = availability[p]
                    yield RadioButton(
                        _provider_label(p, avail),
                        id=f"adv-{p}",
                        disabled=not avail,
                    )
            yield Label("Adversarial LLM Model Name", classes="field-label")
            yield Input(placeholder="e.g. gpt-4o-mini / claude-3-5-sonnet-20241022", id="adv_llm_name")

            # ── Score LLM provider ─────────────────────────────────────
            yield Label("Score LLM Provider", classes="field-label")
            with RadioSet(id="score-provider-radio"):
                for p in _PROVIDERS:
                    avail = availability[p]
                    yield RadioButton(
                        _provider_label(p, avail),
                        id=f"score-{p}",
                        disabled=not avail,
                    )
            yield Label("Score LLM Model Name", classes="field-label")
            yield Input(placeholder="e.g. gpt-4o-mini / claude-3-5-sonnet-20241022", id="score_llm_name")

            yield Label(
                "API keys are read from environment variables. See setup_env.sh for details.",
                classes="field-label",
            )
            with Horizontal():
                yield Button("Save",   id="btn-save",   variant="primary")
                yield Button("Cancel", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        s = self.app.settings
        target_type = s.get("target_type", "http")

        for field_id, *_ in _HTTP_FIELDS + _BROWSER_FIELDS:
            widget = self.query_one(f"#{field_id}", Input)
            widget.value = s.get(field_id, "")

        self.query_one("#adv_llm_name",   Input).value = s.get("adv_llm_name",   "")
        self.query_one("#score_llm_name", Input).value = s.get("score_llm_name", "")

        self._apply_target_type(target_type)

        if target_type == "browser":
            self.query_one("#radio-browser", RadioButton).value = True
        else:
            self.query_one("#radio-http", RadioButton).value = True

        # Restore saved provider selections
        adv_provider   = s.get("adv_llm_provider",   "openai")
        score_provider = s.get("score_llm_provider", "openai")
        self._select_provider("adv",   adv_provider)
        self._select_provider("score", score_provider)

    def _apply_target_type(self, target_type: str) -> None:
        http_cfg    = self.query_one("#http-config")
        browser_cfg = self.query_one("#browser-config")
        if target_type == "browser":
            http_cfg.display    = False
            browser_cfg.display = True
        else:
            http_cfg.display    = True
            browser_cfg.display = False

    def _select_provider(self, role: str, provider: str) -> None:
        """Select the RadioButton for the given provider, if it is enabled."""
        btn_id = f"{role}-{provider}"
        try:
            btn = self.query_one(f"#{btn_id}", RadioButton)
            if not btn.disabled:
                btn.value = True
        except Exception:
            pass

    def _selected_provider(self, radio_id: str) -> str:
        """Return the provider key for the currently selected RadioButton."""
        radio_set = self.query_one(f"#{radio_id}", RadioSet)
        for p in _PROVIDERS:
            prefix = radio_id.split("-")[0]  # "adv" or "score"
            btn_id = f"{prefix}-{p}"
            try:
                btn = self.query_one(f"#{btn_id}", RadioButton)
                if btn.value:
                    return p
            except Exception:
                pass
        return "openai"

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        if event.radio_set.id == "target-type-radio":
            target_type = "browser" if event.index == 1 else "http"
            self._apply_target_type(target_type)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-save":
            is_browser  = self.query_one("#radio-browser", RadioButton).value
            target_type = "browser" if is_browser else "http"

            updates = {"target_type": target_type}
            for fid, *_ in _HTTP_FIELDS + _BROWSER_FIELDS:
                updates[fid] = self.query_one(f"#{fid}", Input).value

            updates["adv_llm_provider"]   = self._selected_provider("adv-provider-radio")
            updates["score_llm_provider"] = self._selected_provider("score-provider-radio")
            updates["adv_llm_name"]       = self.query_one("#adv_llm_name",   Input).value
            updates["score_llm_name"]     = self.query_one("#score_llm_name", Input).value

            self.app.update_settings(updates)
            self.notify("Settings saved.", title="Saved", severity="information")
            self.app.pop_screen()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()

    def action_go_back(self) -> None:
        self.app.pop_screen()
