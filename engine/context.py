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
