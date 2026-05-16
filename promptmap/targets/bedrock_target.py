from __future__ import annotations

import asyncio
import json
import os
import uuid

import boto3

from engine.base_target import TargetAdapter
from engine.tool_call import (
    ToolCall, ToolCallFunction, ToolCallMessage, ToolCallChoice, ToolCallResponse,
)


class BedrockTargetAdapter(TargetAdapter):
    """
    Amazon Bedrock chat target using the Converse API.
    Supports Claude, Llama, Titan, Mistral and other Bedrock model families.
    Credentials are read from standard AWS environment variables.
    """

    def __init__(self, model: str, region: str = "us-east-1"):
        self._model = model
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._conversations: dict[str, list[dict]] = {}
        self._system_prompts: dict[str, str] = {}

    async def send(self, prompt: str, conversation_id: str) -> str:
        history = self._conversations.setdefault(conversation_id, [])
        history.append({"role": "user", "content": [{"text": prompt}]})

        kwargs: dict = {"modelId": self._model, "messages": history}
        if system := self._system_prompts.get(conversation_id):
            kwargs["system"] = [{"text": system}]

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._client.converse(**kwargs)
        )

        reply = response["output"]["message"]["content"][0]["text"]
        history.append({"role": "assistant", "content": [{"text": reply}]})
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
        system, bedrock_messages = _to_bedrock_messages(messages)
        bedrock_tools = _to_bedrock_tools(tools)

        kwargs: dict = {
            "modelId": self._model,
            "messages": bedrock_messages,
            "toolConfig": {"tools": bedrock_tools},
        }
        if system:
            kwargs["system"] = [{"text": system}]

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None, lambda: self._client.converse(**kwargs)
        )
        return _from_bedrock_response(response)


# ---------------------------------------------------------------------------
# Format converters
# ---------------------------------------------------------------------------

def _to_bedrock_messages(messages: list[dict]) -> tuple[str, list[dict]]:
    """Convert OpenAI-format messages to Bedrock Converse API format."""
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
                "toolResult": {
                    "toolUseId": msg.get("tool_call_id", ""),
                    "content": [{"text": msg.get("content", "")}],
                }
            })
            continue

        if pending_tool_results:
            result.append({"role": "user", "content": pending_tool_results})
            pending_tool_results = []

        if role == "user":
            result.append({"role": "user", "content": [{"text": msg.get("content", "")}]})

        elif role == "assistant":
            content: list[dict] = []
            if msg.get("content"):
                content.append({"text": msg["content"]})
            for tc in (msg.get("tool_calls") or []):
                fn = tc.get("function", {})
                content.append({
                    "toolUse": {
                        "toolUseId": tc.get("id", ""),
                        "name": fn.get("name", ""),
                        "input": json.loads(fn.get("arguments", "{}")),
                    }
                })
            if content:
                result.append({"role": "assistant", "content": content})

    if pending_tool_results:
        result.append({"role": "user", "content": pending_tool_results})

    return system, result


def _to_bedrock_tools(tools: list[dict]) -> list[dict]:
    """Convert OpenAI-format tool definitions to Bedrock toolSpec format."""
    result = []
    for tool in tools:
        fn = tool.get("function", {})
        result.append({
            "toolSpec": {
                "name": fn.get("name", ""),
                "description": fn.get("description", ""),
                "inputSchema": {"json": fn.get("parameters", {})},
            }
        })
    return result


def _from_bedrock_response(response: dict) -> ToolCallResponse:
    """Convert Bedrock Converse API response to common ToolCallResponse."""
    tool_calls: list[ToolCall] = []
    text_content: str | None = None

    output_msg = response.get("output", {}).get("message", {})
    for block in output_msg.get("content", []):
        if "toolUse" in block:
            tu = block["toolUse"]
            tool_calls.append(ToolCall(
                id=tu.get("toolUseId", str(uuid.uuid4())),
                function=ToolCallFunction(
                    name=tu.get("name", ""),
                    arguments=json.dumps(tu.get("input", {})),
                ),
            ))
        elif "text" in block:
            text_content = block["text"]

    finish_reason = "tool_calls" if tool_calls else "stop"

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
