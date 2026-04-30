from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class ToolCallFunction:
    name: str
    arguments: str  # JSON string


@dataclass
class ToolCall:
    id: str
    function: ToolCallFunction


@dataclass
class ToolCallMessage:
    tool_calls: list[ToolCall] | None = None
    content: str | None = None

    def model_dump(self) -> dict:
        result: dict = {"role": "assistant"}
        if self.content is not None:
            result["content"] = self.content
        if self.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        return result


@dataclass
class ToolCallChoice:
    finish_reason: str
    message: ToolCallMessage


@dataclass
class ToolCallResponse:
    choices: list[ToolCallChoice]
