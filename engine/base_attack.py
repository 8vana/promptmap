from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from .models import AttackResult

if TYPE_CHECKING:
    from .context import AttackContext


class BaseAttack(ABC):
    @abstractmethod
    async def run(self, ctx: "AttackContext", objective: str, **kwargs) -> AttackResult: ...
