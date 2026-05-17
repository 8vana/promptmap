"""PromptMap — automated AI red-teaming framework.

Public API surface — the contract downstream consumers (e.g. AgenticMap) pin to:

- ``TargetAdapter``, ``BaseAttack``, ``AttackContext``      ── engine contracts
- ``AttackResult``, ``ScorerResult``, ``Message``           ── result / data shapes
- ``ToolCall``, ``ToolCallFunction``, ``ToolCallMessage``,
  ``ToolCallChoice``, ``ToolCallResponse``                  ── tool-call protocol

Changing the signature of anything re-exported here is a breaking change and
requires a major version bump. Deep imports (e.g.
``from promptmap.engine.base_target import TargetAdapter``) remain available
for advanced use but are not part of the stability contract.
"""

from promptmap.engine.base_target import TargetAdapter
from promptmap.engine.base_attack import BaseAttack
from promptmap.engine.context import AttackContext
from promptmap.engine.models import AttackResult, Message, ScorerResult
from promptmap.engine.tool_call import (
    ToolCall,
    ToolCallChoice,
    ToolCallFunction,
    ToolCallMessage,
    ToolCallResponse,
)

__all__ = [
    "TargetAdapter",
    "BaseAttack",
    "AttackContext",
    "AttackResult",
    "Message",
    "ScorerResult",
    "ToolCall",
    "ToolCallChoice",
    "ToolCallFunction",
    "ToolCallMessage",
    "ToolCallResponse",
]

__version__ = "0.1.0"
