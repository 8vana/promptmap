from pyrit.prompt_converter import PromptConverter


class Base64Converter(PromptConverter):
    async def convert_tokens_async(self, prompt: str) -> str:
        # Please implement custom logic.
        return f"[CustomConverted] {prompt}"
