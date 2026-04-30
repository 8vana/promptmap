from __future__ import annotations

import json
import os
import uuid

from google import genai
from google.genai import types

from engine.base_target import TargetAdapter
from engine.tool_call import (
    ToolCall, ToolCallFunction, ToolCallMessage, ToolCallChoice, ToolCallResponse,
)


class GeminiTargetAdapter(TargetAdapter):
    """
    Google Gemini chat target using the google-genai SDK.
    Manages per-conversation history keyed by conversation_id.
    Reads GEMINI_API_KEY or GOOGLE_API_KEY from environment.
    """

    def __init__(self, model: str, api_key: str = ""):
        self._model = model
        resolved_key = api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", "")
        self._client = genai.Client(api_key=resolved_key)
        self._conversations: dict[str, list[types.Content]] = {}
        self._system_prompts: dict[str, str] = {}

    async def send(self, prompt: str, conversation_id: str) -> str:
        history = self._conversations.setdefault(conversation_id, [])
        history.append(types.Content(role="user", parts=[types.Part(text=prompt)]))

        config = types.GenerateContentConfig()
        if system := self._system_prompts.get(conversation_id):
            config.system_instruction = system

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=history,
            config=config,
        )
        reply = response.text or ""
        history.append(types.Content(role="model", parts=[types.Part(text=reply)]))
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
        system, contents = _to_gemini_contents(messages)
        gemini_tools = _to_gemini_tools(tools)

        config = types.GenerateContentConfig(tools=gemini_tools)
        if system:
            config.system_instruction = system

        response = await self._client.aio.models.generate_content(
            model=self._model,
            contents=contents,
            config=config,
        )
        return _from_gemini_response(response)


# ---------------------------------------------------------------------------
# Format converters
# ---------------------------------------------------------------------------

def _to_gemini_contents(messages: list[dict]) -> tuple[str, list[types.Content]]:
    """Convert OpenAI-format messages to Gemini Content list."""
    system = ""
    contents: list[types.Content] = []

    # Pre-build tool_call_id → function_name map for tool result conversion
    tool_id_to_name: dict[str, str] = {}
    for msg in messages:
        if msg.get("role") == "assistant":
            for tc in (msg.get("tool_calls") or []):
                tool_id_to_name[tc["id"]] = tc["function"]["name"]

    for msg in messages:
        role = msg.get("role")

        if role == "system":
            system = msg.get("content", "")
            continue

        if role == "user":
            contents.append(types.Content(
                role="user",
                parts=[types.Part(text=msg.get("content", ""))],
            ))

        elif role == "assistant":
            parts: list[types.Part] = []
            if msg.get("content"):
                parts.append(types.Part(text=msg["content"]))
            for tc in (msg.get("tool_calls") or []):
                fn = tc.get("function", {})
                parts.append(types.Part(function_call=types.FunctionCall(
                    name=fn.get("name", ""),
                    args=json.loads(fn.get("arguments", "{}")),
                )))
            if parts:
                contents.append(types.Content(role="model", parts=parts))

        elif role == "tool":
            fn_name = tool_id_to_name.get(msg.get("tool_call_id", ""), "unknown")
            contents.append(types.Content(
                role="user",
                parts=[types.Part(function_response=types.FunctionResponse(
                    name=fn_name,
                    response={"result": msg.get("content", "")},
                ))],
            ))

    return system, contents


def _to_gemini_tools(tools: list[dict]) -> list[types.Tool]:
    """Convert OpenAI-format tool definitions to Gemini Tool list."""
    declarations: list[types.FunctionDeclaration] = []
    for tool in tools:
        fn = tool.get("function", {})
        declarations.append(types.FunctionDeclaration(
            name=fn.get("name", ""),
            description=fn.get("description", ""),
            parameters=_convert_schema(fn.get("parameters", {})),
        ))
    return [types.Tool(function_declarations=declarations)]


def _convert_schema(schema: dict) -> types.Schema:
    """Recursively convert JSON Schema dict to Gemini Schema."""
    schema_type = schema.get("type", "string").upper()
    properties: dict[str, types.Schema] = {}
    for prop_name, prop_schema in schema.get("properties", {}).items():
        properties[prop_name] = types.Schema(
            type=prop_schema.get("type", "string").upper(),
            description=prop_schema.get("description", ""),
        )
    return types.Schema(
        type=schema_type,
        properties=properties or None,
        required=schema.get("required") or None,
    )


def _from_gemini_response(response) -> ToolCallResponse:
    """Convert Gemini response to common ToolCallResponse."""
    tool_calls: list[ToolCall] = []
    text_content: str | None = None

    if response.candidates:
        candidate = response.candidates[0]
        if candidate.content and candidate.content.parts:
            for part in candidate.content.parts:
                if getattr(part, "function_call", None):
                    tool_calls.append(ToolCall(
                        id=f"call_{uuid.uuid4().hex[:8]}",
                        function=ToolCallFunction(
                            name=part.function_call.name,
                            arguments=json.dumps(dict(part.function_call.args)),
                        ),
                    ))
                elif getattr(part, "text", None):
                    text_content = part.text

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
