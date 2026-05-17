"""BaseAttack — PromptMap public API.

Defines the contract every attack strategy (single-shot PI, Crescendo, PAIR,
TAP, Chunked Request, Agent, …) implements. Downstream consumers (e.g.
AgenticMap) depend on this signature. Changing ``BaseAttack.run`` is a
breaking change and requires a major version bump.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .models import AttackResult

if TYPE_CHECKING:
    from .context import AttackContext


class BaseAttack(ABC):
    @abstractmethod
    async def run(self, ctx: "AttackContext", objective: str, **kwargs) -> AttackResult: ...
