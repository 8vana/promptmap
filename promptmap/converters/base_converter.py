from abc import ABC, abstractmethod


class BaseConverter(ABC):
    @abstractmethod
    async def convert(self, prompt: str) -> str: ...
