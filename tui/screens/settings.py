from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, Footer, Header, Input, Label, RadioSet, RadioButton
from textual.containers import Container, Horizontal, VerticalScroll

from targets.factory import get_available_providers, get_missing_env_vars, PROVIDER_LABELS
from utils import LANGUAGE_DISPLAY_NAMES, SUPPORTED_LANGUAGES

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
        # 保存済み target_type を読み出し、ラジオの初期値に直接渡す。
        # （on_mount で .value = True を呼ぶ方式は RadioSet.Changed の遅延発火と
        #   レースし、表示切替が巻き戻る問題を起こすため避ける）
        initial_target_type = self.app.settings.get("target_type", "http")

        yield Header()
        with VerticalScroll(classes="settings-form"):
            yield Label("⚙  Settings", classes="panel-title")

            # ── Target type ────────────────────────────────────────────
            yield Label("Target Type", classes="field-label")
            with RadioSet(id="target-type-radio"):
                yield RadioButton("HTTP API",    id="radio-http",
                                  value=(initial_target_type == "http"))
                yield RadioButton("Web Browser", id="radio-browser",
                                  value=(initial_target_type == "browser"))

            # ── HTTP config ────────────────────────────────────────────
            with Container(id="http-config"):
                yield Label("─── HTTP API target ───", classes="section-divider")
                for field_id, label_text, placeholder in _HTTP_FIELDS:
                    yield Label(label_text, classes="field-label")
                    yield Input(placeholder=placeholder, id=field_id)

            # ── Browser config ─────────────────────────────────────────
            with Container(id="browser-config"):
                yield Label("─── Web Browser target ───", classes="section-divider")
                yield Label("Browser Config Path (YAML)", classes="field-label")
                with Horizontal(id="browser-config-row"):
                    yield Input(
                        placeholder="/path/to/browser_target.yaml",
                        id="browser_config_path",
                    )
                    yield Button("Browse…", id="btn-browse-yaml")
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

            # ── Target language ────────────────────────────────────────
            yield Label("Target Language", classes="field-label")
            with RadioSet(id="target-language-radio"):
                for lang in SUPPORTED_LANGUAGES:
                    yield RadioButton(
                        f"{LANGUAGE_DISPLAY_NAMES.get(lang, lang)} ({lang})",
                        id=f"lang-{lang}",
                    )
            yield Label(
                "Determines which language signatures / jailbreak templates / response "
                "encodings are used. Falls back to English when a translation is missing.",
                classes="field-label",
            )

            yield Label(
                "API keys are read from environment variables. See setup_env.sh.example for details.",
                classes="field-label",
            )

        # ボタン行はスクロール領域の外に固定表示
        with Horizontal(id="settings-buttons"):
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

        # ラジオの初期選択は compose で済ませてあるため、ここでは display 切替のみ。
        self._apply_target_type(target_type)

        # Restore saved provider selections
        adv_provider   = s.get("adv_llm_provider",   "openai")
        score_provider = s.get("score_llm_provider", "openai")
        self._select_provider("adv",   adv_provider)
        self._select_provider("score", score_provider)

        # Restore saved target_language selection
        target_lang = s.get("target_language", "en")
        if target_lang not in SUPPORTED_LANGUAGES:
            target_lang = "en"
        self._select_language(target_lang)

    def _apply_target_type(self, target_type: str) -> None:
        """Toggle the HTTP / Browser sections via Textual's standard
        `widget.display` property only.
        """
        self.query_one("#http-config").display    = (target_type == "http")
        self.query_one("#browser-config").display = (target_type == "browser")

    def on_radio_set_changed(self, event: RadioSet.Changed) -> None:
        # event.index ではなく実際のラジオの値を直接 query する。
        # プログラム経由の値変更でイベントが遅延発火しても、常に正しい
        # 結果を返す（冪等）。
        if event.radio_set.id == "target-type-radio":
            is_browser = self.query_one("#radio-browser", RadioButton).value
            self._apply_target_type("browser" if is_browser else "http")

    def _select_provider(self, role: str, provider: str) -> None:
        """Select the RadioButton for the given provider, if it is enabled."""
        btn_id = f"{role}-{provider}"
        try:
            btn = self.query_one(f"#{btn_id}", RadioButton)
            if not btn.disabled:
                btn.value = True
        except Exception:
            pass

    def _select_language(self, lang: str) -> None:
        try:
            self.query_one(f"#lang-{lang}", RadioButton).value = True
        except Exception:
            pass

    def _selected_language(self) -> str:
        for lang in SUPPORTED_LANGUAGES:
            try:
                if self.query_one(f"#lang-{lang}", RadioButton).value:
                    return lang
            except Exception:
                pass
        return "en"

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
            updates["target_language"]    = self._selected_language()

            self.app.update_settings(updates)

            # ファイル存在チェック（browser_config_path）。保存はブロックしないが警告は出す。
            import os
            if target_type == "browser":
                path = updates.get("browser_config_path", "").strip()
                if path and not os.path.isfile(os.path.expanduser(path)):
                    self.notify(
                        f"Saved, but Browser Config Path does not exist:\n{path}",
                        title="Warning",
                        severity="warning",
                        timeout=6,
                    )
                else:
                    self.notify("Settings saved.", title="Saved", severity="information")
            else:
                self.notify("Settings saved.", title="Saved", severity="information")

            self.app.pop_screen()
        elif event.button.id == "btn-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-browse-yaml":
            self._open_file_picker()

    def _open_file_picker(self) -> None:
        """Open the YAML file picker modal and put the chosen path into the input."""
        from tui.screens.file_picker import FilePickerScreen
        current = self.query_one("#browser_config_path", Input).value

        def _on_dismiss(picked: str | None) -> None:
            if picked:
                self.query_one("#browser_config_path", Input).value = picked

        self.app.push_screen(FilePickerScreen(start_path=current), _on_dismiss)

    def action_go_back(self) -> None:
        self.app.pop_screen()
