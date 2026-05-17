"""TargetAdapter — PromptMap public API.

Defines the contract that every concrete target (LLM provider, HTTP endpoint,
browser-driven chat UI, …) implements so attacks can talk to it uniformly.

Downstream consumers (e.g. AgenticMap) depend on these signatures. Changing
``TargetAdapter.send`` or ``TargetAdapter.chat_with_tools`` is a breaking
change and requires a major version bump.
"""

from abc import ABC, abstractmethod

from promptmap.engine.tool_call import ToolCallResponse


class TargetAdapter(ABC):
    @abstractmethod
    async def send(self, prompt: str, conversation_id: str) -> str: ...

    def set_system_prompt(self, system_prompt: str, conversation_id: str) -> None:
        """Set a system prompt for a conversation. No-op for stateless targets."""

    def reset_conversation(self, conversation_id: str) -> None:
        """Clear conversation history. No-op for stateless targets."""

    async def close(self) -> None:
        """Release any resources held by the target. No-op for stateless targets."""

    async def chat_with_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> ToolCallResponse:
        raise NotImplementedError(
            f"{type(self).__name__} does not support tool calling."
        )
