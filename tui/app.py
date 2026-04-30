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
        data = dict(_DEFAULT_SETTINGS)
        if os.path.exists(_CONFIG_FILE):
            try:
                with open(_CONFIG_FILE) as f:
                    data.update(json.load(f))
            except Exception:
                pass
        return data

    def _save_settings(self) -> None:
        try:
            with open(_CONFIG_FILE, "w") as f:
                json.dump(self._settings, f, indent=2)
        except Exception:
            pass

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
        s = self._settings

        if s.get("target_type") == "browser":
            from targets.browser_config import load_browser_config
            from targets.playwright_target import PlaywrightTargetAdapter
            cfg = load_browser_config(s["browser_config_path"])
            objective_target = PlaywrightTargetAdapter(cfg)
        else:
            objective_target = HTTPTargetAdapter(
                endpoint=s["api_endpoint"],
                body_template=json.loads(s.get("body_template", '{"text": "{PROMPT}"}')),
                response_key=s.get("response_key", "text"),
            )

        adversarial_target = create_target_adapter(
            provider=s["adv_llm_provider"],
            model=s["adv_llm_name"],
        )
        score_llm = create_target_adapter(
            provider=s["score_llm_provider"],
            model=s["score_llm_name"],
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
