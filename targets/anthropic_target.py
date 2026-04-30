from __future__ import annotations

import json

from anthropic import AsyncAnthropic

from engine.base_target import TargetAdapter
from engine.tool_call import (
    ToolCall, ToolCallFunction, ToolCallMessage, ToolCallChoice, ToolCallResponse,
)


class AnthropicTargetAdapter(TargetAdapter):
    """
    Anthropic Claude chat target.
    Manages per-conversation history keyed by conversation_id.
    """

    def __init__(self, model: str, api_key: str):
        self._model = model
        self._client = AsyncAnthropic(api_key=api_key)
        self._conversations: dict[str, list[dict]] = {}
        self._system_prompts: dict[str, str] = {}

    async def send(self, prompt: str, conversation_id: str) -> str:
        history = self._conversations.setdefault(conversation_id, [])
        history.append({"role": "user", "content": prompt})

        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": history,
        }
        if system := self._system_prompts.get(conversation_id):
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        reply = response.content[0].text if response.content else ""
        history.append({"role": "assistant", "content": reply})
        return reply

    def set_system_prompt(self, system_prompt: str, conversation_id: str) -> None:
        self._conversations[conversation_id] = []
        self._system_prompts[conversation_id] = system_prompt

    def reset_conversation(self, conversation_id: str) -> None:
        self._conversations.pop(conversation_id, None)
        self._system_prompts.pop(conversation_id, None)

    async def chat_with_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> ToolCallResponse:
        system, anthropic_messages = _to_anthropic_messages(messages)
        anthropic_tools = _to_anthropic_tools(tools)

        kwargs: dict = {
            "model": self._model,
            "max_tokens": 4096,
            "messages": anthropic_messages,
            "tools": anthropic_tools,
        }
        if system:
            kwargs["system"] = system

        response = await self._client.messages.create(**kwargs)
        return _from_anthropic_response(response)


# ---------------------------------------------------------------------------
# Format converters
# ---------------------------------------------------------------------------

def _to_anthropic_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Convert OpenAI-format messages to Anthropic format."""
    system = ""
    result: list[dict] = []
    pending_tool_results: list[dict] = []

    for msg in messages:
        role = msg.get("role")

        if role == "system":
            system = msg.get("content", "")
            continue

        if role == "tool":
            pending_tool_results.append({
                "type": "tool_result",
                "tool_use_id": msg.get("tool_call_id", ""),
                "content": msg.get("content", ""),
            })
            continue

        if pending_tool_results:
            result.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

        if role == "user":
            result.append({"role": "user", "content": msg.get("content", "")})

        elif role == "assistant":
            content: list[dict] = []
            if msg.get("content"):
                content.append({"type": "text", "text": msg["content"]})
            for tc in (msg.get("tool_calls") or []):
                fn = tc.get("function", {})
                content.append({
                    "type": "tool_use",
                    "id": tc.get("id", ""),
                    "name": fn.get("name", ""),
                    "input": json.loads(fn.get("arguments", "{}")),
                })
            if content:
                result.append({"role": "assistant", "content": content})

    if pending_tool_results:
        result.append({"role": "user", "content": pending_tool_results})

    return system, result


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tool definitions to Anthropic format."""
    result = []
    for tool in tools:
        fn = tool.get("function", {})
        result.append({
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {}),
        })
    return result


def _from_anthropic_response(response) -> ToolCallResponse:
    """Convert Anthropic response to common ToolCallResponse."""
    tool_calls: list[ToolCall] = []
    text_content: str | None = None

    for block in response.content:
        if block.type == "tool_use":
            tool_calls.append(ToolCall(
                id=block.id,
                function=ToolCallFunction(
                    name=block.name,
                    arguments=json.dumps(block.input),
                ),
            ))
        elif block.type == "text":
            text_content = block.text

    if response.stop_reason == "tool_use":
        finish_reason = "tool_calls"
    else:
        finish_reason = "stop"

    return ToolCallResponse(
        choices=[
            ToolCallChoice(
                finish_reason=finish_reason,
                message=ToolCallMessage(
                    tool_calls=tool_calls if tool_calls else None,
                    content=text_content,
                ),
            )
        ]
    )
