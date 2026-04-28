from __future__ import annotations

import asyncio
import json
import os

from textual.app import App, ComposeResult
from textual.binding import Binding

from engine.context import AttackContext
from memory.session_memory import SessionMemory
from targets.http_target import HTTPTargetAdapter
from targets.openai_target import OpenAITargetAdapter
from scorers.llm_judge import LLMJudgeScorer
from attacks.single_pi_attack import SinglePIAttack
from attacks.multi_crescendo_attack import CrescendoAttack
from attacks.multi_pair_attack import PAIRAttack
from attacks.multi_red_teaming_attack import RedTeamingAttack

_CONFIG_FILE = os.path.expanduser("~/.promptmap_config.json")

_DEFAULT_SETTINGS: dict = {
    "api_endpoint":   "",
    "body_template":  '{"text": "{PROMPT}"}',
    "response_key":   "text",
    "adv_llm_name":   "",
    "score_llm_name": "",
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
        # Always pull API keys from env (never persist them to disk)
        data["adv_llm_api_key"]   = os.getenv("ADV_LLM_API_KEY",   data.get("adv_llm_api_key",   ""))
        data["score_llm_api_key"] = os.getenv("SCORE_LLM_API_KEY", data.get("score_llm_api_key", ""))
        return data

    def _save_settings(self) -> None:
        safe = {k: v for k, v in self._settings.items()
                if k not in ("adv_llm_api_key", "score_llm_api_key")}
        try:
            with open(_CONFIG_FILE, "w") as f:
                json.dump(safe, f, indent=2)
        except Exception:
            pass

    def settings_ready(self) -> bool:
        s = self._settings
        return all([
            s.get("api_endpoint"),
            s.get("adv_llm_name"),
            s.get("adv_llm_api_key"),
            s.get("score_llm_name"),
            s.get("score_llm_api_key"),
        ])

    # ------------------------------------------------------------------ #
    #  AttackContext factory                                               #
    # ------------------------------------------------------------------ #

    def build_context(self, converter_instances: list | None = None) -> AttackContext:
        s = self._settings

        objective_target = HTTPTargetAdapter(
            endpoint=s["api_endpoint"],
            body_template=json.loads(s.get("body_template", '{"text": "{PROMPT}"}')),
            response_key=s.get("response_key", "text"),
        )
        adversarial_target = OpenAITargetAdapter(
            model=s["adv_llm_name"],
            api_key=s["adv_llm_api_key"],
        )
        score_llm = OpenAITargetAdapter(
            model=s["score_llm_name"],
            api_key=s["score_llm_api_key"],
        )
        scorer = LLMJudgeScorer(judge_target=score_llm)

        available_attacks: dict = {
            "Single_PI_Attack":          SinglePIAttack(),
            "Multi_Crescendo_Attack":    CrescendoAttack(),
            "Multi_PAIR_Attack":         PAIRAttack(),
            "Multi_Red_Teaming_Attack":  RedTeamingAttack(),
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
