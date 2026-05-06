from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from engine.base_attack import BaseAttack
    from engine.base_scorer import BaseScorer
    from engine.base_target import TargetAdapter
    from engine.events import ProgressEvent
    from memory.session_memory import SessionMemory


@dataclass
class AttackContext:
    target: "TargetAdapter"               # The AI system under test
    adversarial_target: "TargetAdapter"   # Adversarial LLM (generates attack prompts)
    scorer: "BaseScorer"                  # LLM-as-a-Judge
    converters: list                      # list[BaseConverter]
    memory: "SessionMemory"
    available_attacks: dict = field(default_factory=dict)  # dict[str, BaseAttack]
    progress_queue: asyncio.Queue | None = None            # TUI progress channel

    async def emit(self, event: "ProgressEvent") -> None:
        """Push a ProgressEvent to the TUI queue, or fall back to CLI print."""
        if self.progress_queue is not None:
            await self.progress_queue.put(event)
        else:
            from engine.events import fmt_cli
            fmt_cli(event)

    async def close_all_targets(self) -> None:
        """Release any resources held by the three target adapters.

        Called from screens after an attack run completes so that long-lived
        resources (Playwright browser process, HTTP sessions, etc.) are released
        before the asyncio loop is torn down. Each close() is best-effort —
        failures are logged but never re-raised.
        """
        from engine.logging_setup import get_logger
        log = get_logger("engine.context")

        # Scorer's judge_target may be wrapped behind .judge attribute or _judge
        judge_target = getattr(self.scorer, "_judge", None) or getattr(self.scorer, "judge", None)
        for label, t in (
            ("target",      self.target),
            ("adversarial", self.adversarial_target),
            ("scorer",      judge_target),
        ):
            if t is None:
                continue
            try:
                await t.close()
            except Exception:
                log.exception("Failed to close %s target", label)
