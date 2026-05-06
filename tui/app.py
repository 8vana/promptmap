from __future__ import annotations

import asyncio
import json
import os

from textual.app import App, ComposeResult
from textual.binding import Binding

from engine.context import AttackContext
from memory.session_memory import SessionMemory
from targets.http_target import HTTPTargetAdapter
from targets.factory import create_target_adapter, get_available_providers, get_missing_env_vars, PROVIDER_LABELS
from scorers.llm_judge import LLMJudgeScorer
from attacks.single_pi_attack import SinglePIAttack
from attacks.multi_crescendo_attack import CrescendoAttack
from attacks.multi_pair_attack import PAIRAttack
from attacks.multi_tap_attack import TAPAttack
from attacks.multi_chunked_request_attack import ChunkedRequestAttack

_CONFIG_FILE = os.path.expanduser("~/.promptmap_config.json")

_DEFAULT_SETTINGS: dict = {
    "api_endpoint":       "",
    "body_template":      '{"text": "{PROMPT}"}',
    "response_key":       "text",
    "adv_llm_provider":   "openai",
    "adv_llm_name":       "",
    "score_llm_provider": "openai",
    "score_llm_name":     "",
}

# Setting key -> environment variable name. When the env var is set,
# its value overrides whatever was loaded from _CONFIG_FILE.
# Kept in sync with PromptMapInteractiveShell._ENV_OVERRIDES in promptmap.py.
_ENV_OVERRIDES: dict[str, str] = {
    "adv_llm_provider":   "PROMPTMAP_ADV_LLM_PROVIDER",
    "adv_llm_name":       "PROMPTMAP_ADV_LLM_NAME",
    "score_llm_provider": "PROMPTMAP_SCORE_LLM_PROVIDER",
    "score_llm_name":     "PROMPTMAP_SCORE_LLM_NAME",
}


class PromptMapApp(App):
    """PromptMap – AI Red-Teaming TUI"""

    CSS_PATH = "promptmap.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", priority=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._settings: dict = self._load_settings()
        self.session_memory: SessionMemory = SessionMemory()

    # ------------------------------------------------------------------ #
    #  Lifecycle                                                           #
    # ------------------------------------------------------------------ #

    def on_mount(self) -> None:
        from tui.screens.home import HomeScreen
        self.push_screen(HomeScreen())

    # ------------------------------------------------------------------ #
    #  Settings helpers                                                    #
    # ------------------------------------------------------------------ #

    @property
    def settings(self) -> dict:
        return self._settings

    def update_settings(self, updates: dict) -> None:
        self._settings.update(updates)
        self._save_settings()

    def _load_settings(self) -> dict:
        from engine.logging_setup import get_logger
        log = get_logger("tui.settings")
        data = dict(_DEFAULT_SETTINGS)
        if os.path.exists(_CONFIG_FILE):
            try:
                with open(_CONFIG_FILE) as f:
                    data.update(json.load(f))
                log.debug("Loaded settings from %s", _CONFIG_FILE)
            except Exception:
                log.exception("Failed to load settings from %s", _CONFIG_FILE)

        for key, env_name in _ENV_OVERRIDES.items():
            value = (os.getenv(env_name) or "").strip()
            if value:
                data[key] = value
                log.info("Settings: '%s' overridden by $%s", key, env_name)
        return data

    def _save_settings(self) -> None:
        from engine.logging_setup import get_logger
        log = get_logger("tui.settings")
        try:
            with open(_CONFIG_FILE, "w") as f:
                json.dump(self._settings, f, indent=2)
            log.debug("Saved settings to %s", _CONFIG_FILE)
        except Exception:
            log.exception("Failed to save settings to %s", _CONFIG_FILE)

    def settings_ready(self) -> bool:
        s = self._settings
        availability = get_available_providers()

        if s.get("target_type") == "browser":
            target_ready = bool(s.get("browser_config_path"))
        else:
            target_ready = bool(s.get("api_endpoint"))

        adv_provider   = s.get("adv_llm_provider", "openai")
        score_provider = s.get("score_llm_provider", "openai")

        return all([
            target_ready,
            s.get("adv_llm_name"),
            availability.get(adv_provider, False),
            s.get("score_llm_name"),
            availability.get(score_provider, False),
        ])

    def get_provider_warnings(self) -> list[str]:
        """Return warning messages for providers whose env vars are missing."""
        s = self._settings
        warnings: list[str] = []
        for role, provider_key in [("Adversarial LLM", "adv_llm_provider"),
                                    ("Score LLM",       "score_llm_provider")]:
            provider = s.get(provider_key, "openai")
            missing = get_missing_env_vars(provider)
            if missing:
                label = PROVIDER_LABELS.get(provider, provider)
                warnings.append(
                    f"{role} ({label}): set {' or '.join(missing)}"
                    if provider == "gemini" else
                    f"{role} ({label}): set {', '.join(missing)}"
                )
        return warnings

    # ------------------------------------------------------------------ #
    #  AttackContext factory                                               #
    # ------------------------------------------------------------------ #

    def build_context(self, converter_instances: list | None = None) -> AttackContext:
        from engine.logged_target import LoggedTargetAdapter
        s = self._settings

        if s.get("target_type") == "browser":
            from targets.browser_config import load_browser_config
            from targets.playwright_target import PlaywrightTargetAdapter
            cfg = load_browser_config(s["browser_config_path"])
            raw_target = PlaywrightTargetAdapter(cfg)
            target_system, target_model = "browser_target", s.get("browser_config_path", "")
        else:
            raw_target = HTTPTargetAdapter(
                endpoint=s["api_endpoint"],
                body_template=json.loads(s.get("body_template", '{"text": "{PROMPT}"}')),
                response_key=s.get("response_key", "text"),
            )
            target_system, target_model = "http_target", s.get("api_endpoint", "")

        objective_target = LoggedTargetAdapter(
            raw_target, role="target", system=target_system, model=target_model,
        )
        adversarial_target = LoggedTargetAdapter(
            create_target_adapter(provider=s["adv_llm_provider"], model=s["adv_llm_name"]),
            role="adversarial", system=s["adv_llm_provider"], model=s["adv_llm_name"],
        )
        score_llm = LoggedTargetAdapter(
            create_target_adapter(provider=s["score_llm_provider"], model=s["score_llm_name"]),
            role="scorer", system=s["score_llm_provider"], model=s["score_llm_name"],
        )
        scorer = LLMJudgeScorer(judge_target=score_llm)

        available_attacks: dict = {
            "Single_PI_Attack":             SinglePIAttack(),
            "Multi_Crescendo_Attack":       CrescendoAttack(),
            "Multi_PAIR_Attack":            PAIRAttack(),
            "Multi_TAP_Attack":             TAPAttack(),
            "Multi_Chunked_Request_Attack": ChunkedRequestAttack(),
        }

        return AttackContext(
            target=objective_target,
            adversarial_target=adversarial_target,
            scorer=scorer,
            converters=converter_instances or [],
            memory=self.session_memory,
            available_attacks=available_attacks,
            progress_queue=asyncio.Queue(),
        )
