"""JSONL conversation telemetry — local fallback for OTEL.

Every LLM interaction (Adversarial / Target / Scorer) gets one line in
``~/.promptmap/runs/<run_id>.jsonl``. Field names lean on the OTEL GenAI
semantic convention so the same emitter can later be swapped for an OTLP
exporter without touching call sites.

Shape of one line (subset shown):

    {
      "trace_id":         "<uuid>",         # = run_id, one per process
      "span_id":          "<uuid>",         # one per LLM call
      "parent_span_id":   "<uuid>|null",    # for nested spans (turn ⊃ scorer)
      "name":             "llm.call",
      "start_time":       "2026-05-06T10:11:12.345Z",
      "end_time":         "2026-05-06T10:11:14.567Z",
      "duration_ms":      2222,
      "attributes": {
        "gen_ai.system":          "anthropic",
        "gen_ai.request.model":   "claude-3-5-sonnet-20241022",
        "promptmap.role":         "target",     # adversarial | target | scorer
        "promptmap.conversation": "<id>",
        "gen_ai.prompt":          "...",        # truncated to 4 KB by default
        "gen_ai.completion":      "..."
      },
      "status": "ok" | "error",
      "error":  "..."                   # only when status == error
    }

Use ``record_call(...)`` as a context manager — start/end timestamps and
duration are filled in automatically; you only need to provide the role,
system, model, prompt, and (on success) response.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from engine.logging_setup import get_logger

_logger = get_logger(__name__)

_RUNS_DIR = Path(os.path.expanduser("~/.promptmap/runs"))
_MAX_PROMPT_CHARS = 4096   # Truncate huge prompts/completions to keep JSONL grep-friendly.


class ConversationLog:
    """JSONL writer for one promptmap process's LLM interactions.

    Thread-safe: writes are serialised on ``self._lock`` so multiple async
    workers can call :meth:`record_call` concurrently without corrupting the
    file.
    """

    def __init__(self, path: Path | str | None = None) -> None:
        if path is None:
            _RUNS_DIR.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            path = _RUNS_DIR / f"{stamp}_{uuid.uuid4().hex[:8]}.jsonl"
        self._path = Path(path)
        self._trace_id = uuid.uuid4().hex
        self._lock = threading.Lock()
        # ファイルを open しっぱなしにするとロック競合の問題があるため、
        # write 都度 open/close する。レコード数は LLM 呼出と同じオーダーで
        # 多くないので I/O 効率は気にしない。
        self._path.touch(exist_ok=True)
        _logger.info("Conversation log → %s (trace_id=%s)", self._path, self._trace_id)

    @property
    def path(self) -> Path:
        return self._path

    @property
    def trace_id(self) -> str:
        return self._trace_id

    @contextmanager
    def record_call(
        self,
        *,
        role: str,                  # "adversarial" | "target" | "scorer"
        system: str,                # "openai" | "anthropic" | "bedrock" | "browser_target" | ...
        model: str,
        prompt: str,
        conversation_id: str = "",
        parent_span_id: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> Iterator["_CallContext"]:
        """Context manager that times an LLM call and emits one JSONL line.

        Usage::

            with conv_log.record_call(role="target", system="anthropic", ...) as call:
                result = await target.send(prompt, conv_id)
                call.set_response(result)
        """
        ctx = _CallContext(
            trace_id=self._trace_id,
            parent_span_id=parent_span_id,
            role=role,
            system=system,
            model=model,
            prompt=prompt,
            conversation_id=conversation_id,
            attributes=attributes or {},
        )
        try:
            yield ctx
        except Exception as exc:
            ctx.set_error(exc)
            raise
        finally:
            self._write(ctx.to_dict())

    def _write(self, record: dict[str, Any]) -> None:
        line = json.dumps(record, ensure_ascii=False, default=str)
        with self._lock:
            with self._path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")


class _CallContext:
    """Mutable record assembled inside :meth:`ConversationLog.record_call`."""

    __slots__ = (
        "trace_id", "span_id", "parent_span_id",
        "role", "system", "model", "prompt", "response",
        "conversation_id", "attributes", "_t0", "_t1",
        "_status", "_error",
    )

    def __init__(
        self,
        trace_id: str,
        parent_span_id: str | None,
        role: str,
        system: str,
        model: str,
        prompt: str,
        conversation_id: str,
        attributes: dict[str, Any],
    ) -> None:
        self.trace_id = trace_id
        self.span_id = uuid.uuid4().hex
        self.parent_span_id = parent_span_id
        self.role = role
        self.system = system
        self.model = model
        self.prompt = prompt
        self.response: str | None = None
        self.conversation_id = conversation_id
        self.attributes = dict(attributes)
        self._t0 = time.perf_counter()
        self._t1: float | None = None
        self._status = "ok"
        self._error: str | None = None

    def set_response(self, response: str) -> None:
        self.response = response

    def set_attribute(self, key: str, value: Any) -> None:
        self.attributes[key] = value

    def set_error(self, exc: BaseException) -> None:
        self._status = "error"
        self._error = f"{type(exc).__name__}: {exc}"

    def to_dict(self) -> dict[str, Any]:
        if self._t1 is None:
            self._t1 = time.perf_counter()
        duration_ms = int((self._t1 - self._t0) * 1000)

        attrs: dict[str, Any] = {
            "gen_ai.system": self.system,
            "gen_ai.request.model": self.model,
            "promptmap.role": self.role,
            "promptmap.conversation": self.conversation_id,
            "gen_ai.prompt": _truncate(self.prompt),
        }
        if self.response is not None:
            attrs["gen_ai.completion"] = _truncate(self.response)
        attrs.update(self.attributes)

        record: dict[str, Any] = {
            "trace_id":       self.trace_id,
            "span_id":        self.span_id,
            "parent_span_id": self.parent_span_id,
            "name":           "llm.call",
            "start_time":     _to_iso8601(self._t0),
            "end_time":       _to_iso8601(self._t1),
            "duration_ms":    duration_ms,
            "attributes":     attrs,
            "status":         self._status,
        }
        if self._error is not None:
            record["error"] = self._error
        return record


def _truncate(text: str, limit: int = _MAX_PROMPT_CHARS) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"…[truncated {len(text) - limit} chars]"


def _to_iso8601(perf_counter_value: float) -> str:
    # perf_counter は単調時計なので、wallclock との差分を都度測って ISO 化する。
    delta = time.perf_counter() - perf_counter_value
    wallclock = datetime.now(timezone.utc).timestamp() - delta
    return datetime.fromtimestamp(wallclock, tz=timezone.utc).isoformat(
        timespec="milliseconds"
    ).replace("+00:00", "Z")


# ─────────────────────────────────────────────────────────────────────────────
# Process-wide singleton (lazy)
# ─────────────────────────────────────────────────────────────────────────────

_active_log: ConversationLog | None = None


def get_conversation_log() -> ConversationLog:
    """Return the process-wide conversation log, creating it on first access."""
    global _active_log
    if _active_log is None:
        _active_log = ConversationLog()
    return _active_log
