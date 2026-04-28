from abc import ABC, abstractmethod

from .models import ScorerResult


class BaseScorer(ABC):
    @abstractmethod
    async def score(self, response: str, objective: str) -> ScorerResult: ...
