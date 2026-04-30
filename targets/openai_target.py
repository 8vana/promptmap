from openai import AsyncOpenAI

from engine.base_target import TargetAdapter
from engine.tool_call import (
    ToolCall, ToolCallFunction, ToolCallMessage, ToolCallChoice, ToolCallResponse,
)


class OpenAITargetAdapter(TargetAdapter):
    """
    OpenAI-compatible chat target.
    Manages per-conversation history keyed by conversation_id.
    Works with any OpenAI-compatible endpoint (OpenAI, Azure, local vLLM, Ollama, etc.).
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        endpoint: str = "https://api.openai.com/v1",
    ):
        self._model = model
        self._client = AsyncOpenAI(api_key=api_key, base_url=endpoint)
        self._conversations: dict[str, list[dict]] = {}

    async def send(self, prompt: str, conversation_id: str) -> str:
        history = self._conversations.setdefault(conversation_id, [])
        history.append({"role": "user", "content": prompt})

        response = await self._client.chat.completions.create(
            model=self._model,
            messages=history,
        )
        reply = response.choices[0].message.content or ""
        history.append({"role": "assistant", "content": reply})
        return reply

    def set_system_prompt(self, system_prompt: str, conversation_id: str) -> None:
        """Initialize (or overwrite) a conversation with a system prompt."""
        self._conversations[conversation_id] = [
            {"role": "system", "content": system_prompt}
        ]

    def reset_conversation(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)

    async def chat_with_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> ToolCallResponse:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
        )
        choice = response.choices[0]
        msg = choice.message

        tool_calls = None
        if msg.tool_calls:
            tool_calls = [
                ToolCall(
                    id=tc.id,
                    function=ToolCallFunction(
                        name=tc.function.name,
                        arguments=tc.function.arguments,
                    ),
                )
                for tc in msg.tool_calls
            ]

        return ToolCallResponse(
            choices=[
                ToolCallChoice(
                    finish_reason=choice.finish_reason or "stop",
                    message=ToolCallMessage(
                        tool_calls=tool_calls,
                        content=msg.content,
                    ),
                )
            ]
        )
