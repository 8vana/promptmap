from abc import ABC, abstractmethod


class BaseConverter(ABC):
    @abstractmethod
    async def convert(self, prompt: str) -> str: ...


class PyRITConverterAdapter(BaseConverter):
    """Wraps a PyRIT PromptConverter behind PromptMap's BaseConverter interface."""

    def __init__(self, pyrit_converter):
        self._converter = pyrit_converter

    async def convert(self, prompt: str) -> str:
        result = await self._converter.convert_async(prompt=prompt)
        return result.output_text
