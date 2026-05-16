"""Transparent wrapper that adds operational logging + JSONL telemetry to any
``TargetAdapter`` without changing its interface.

Usage::

    raw = create_target_adapter(provider="openai", model="gpt-4o-mini")
    target = LoggedTargetAdapter(raw, role="adversarial",
                                 system="openai", model="gpt-4o-mini")

The wrapper:

* Logs every ``send()`` call at DEBUG (prompt length, conversation_id) and
  every failure at ERROR with traceback, via ``promptmap.targets``.
* Emits one JSONL line per call to the process-wide conversation log
  (``engine.conversation_log``).
* Forwards ``set_system_prompt`` / ``reset_conversation`` / ``close`` /
  ``chat_with_tools`` to the inner adapter unchanged.
"""

from __future__ import annotations

from typing import Any

from engine.base_target import TargetAdapter
from engine.conversation_log import ConversationLog, get_conversation_log
from engine.logging_setup import get_logger
from engine.tool_call import ToolCallResponse

_logger = get_logger("targets")


class LoggedTargetAdapter(TargetAdapter):
    """Decorator that adds logs + JSONL telemetry around an inner adapter."""

    def __init__(
        self,
        inner: TargetAdapter,
        *,
        role: str,                     # "adversarial" | "target" | "scorer"
        system: str,                   # provider key, e.g. "openai" / "browser_target"
        model: str,
        conv_log: ConversationLog | None = None,
    ) -> None:
        self._inner = inner
        self._role = role
        self._system = system
        self._model = model
        self._conv_log = conv_log or get_conversation_log()

    async def send(self, prompt: str, conversation_id: str) -> str:
        _logger.debug(
            "send role=%s system=%s model=%s conv=%s prompt_chars=%d",
            self._role, self._system, self._model, conversation_id, len(prompt),
        )
        with self._conv_log.record_call(
            role=self._role,
            system=self._system,
            model=self._model,
            prompt=prompt,
            conversation_id=conversation_id,
        ) as call:
            try:
                response = await self._inner.send(prompt, conversation_id)
            except Exception:
                _logger.exception(
                    "send FAILED role=%s system=%s model=%s conv=%s",
                    self._role, self._system, self._model, conversation_id,
                )
                raise
            call.set_response(response)
            call.set_attribute("gen_ai.response.chars", len(response))
            _logger.debug(
                "send OK role=%s conv=%s response_chars=%d",
                self._role, conversation_id, len(response),
            )
            return response

    def set_system_prompt(self, system_prompt: str, conversation_id: str) -> None:
        _logger.debug(
            "set_system_prompt role=%s conv=%s chars=%d",
            self._role, conversation_id, len(system_prompt),
        )
        self._inner.set_system_prompt(system_prompt, conversation_id)

    def reset_conversation(self, conversation_id: str) -> None:
        _logger.debug("reset_conversation role=%s conv=%s", self._role, conversation_id)
        self._inner.reset_conversation(conversation_id)

    async def close(self) -> None:
        _logger.info("close role=%s system=%s model=%s",
                     self._role, self._system, self._model)
        try:
            await self._inner.close()
        except Exception:
            _logger.exception("close FAILED role=%s", self._role)
            raise

    async def chat_with_tools(
        self, messages: list[dict], tools: list[dict]
    ) -> ToolCallResponse:
        _logger.debug(
            "chat_with_tools role=%s system=%s model=%s msgs=%d tools=%d",
            self._role, self._system, self._model, len(messages), len(tools),
        )
        # tool 用の prompt は messages 全体なので JSON 化したものを記録に残す。
        import json as _json
        prompt_blob = _json.dumps(messages, ensure_ascii=False, default=str)[:4000]
        with self._conv_log.record_call(
            role=self._role,
            system=self._system,
            model=self._model,
            prompt=prompt_blob,
            conversation_id="tools",
            attributes={"promptmap.kind": "chat_with_tools",
                        "promptmap.tools_count": len(tools)},
        ) as call:
            try:
                response = await self._inner.chat_with_tools(messages, tools)
            except Exception:
                _logger.exception(
                    "chat_with_tools FAILED role=%s model=%s",
                    self._role, self._model,
                )
                raise
            call.set_response(_summarise_tool_response(response))
            return response


def _summarise_tool_response(resp: Any) -> str:
    """Best-effort textual summary of ToolCallResponse for the JSONL field."""
    try:
        choice = resp.choices[0]
        msg = choice.message
        if getattr(msg, "tool_calls", None):
            calls = msg.tool_calls or []
            names = ", ".join(getattr(c.function, "name", "?") for c in calls)
            return f"[tool_calls: {names}]"
        return getattr(msg, "content", "") or ""
    except Exception:
        return repr(resp)[:500]
