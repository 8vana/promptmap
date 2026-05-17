"""Core data shapes — PromptMap public API.

``Message``, ``ScorerResult``, and ``AttackResult`` are the values that flow
across PromptMap's public boundary: attacks return them, scorers produce
them, and downstream consumers (e.g. AgenticMap) read their fields directly
to build Findings. Field names and types here are a stability contract —
removing or renaming a field is a breaking change and requires a major
version bump (adding new optional fields is non-breaking).
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Message:
    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ScorerResult:
    score: float    # 0.0 – 1.0 (normalized from 1-10 Likert)
    achieved: bool
    rationale: str = ""


@dataclass
class AttackResult:
    attack_name: str
    objective: str
    achieved: bool
    score: float
    turns: int
    conversation: list = field(default_factory=list)  # list[Message]
    metadata: dict = field(default_factory=dict)
    atlas_techniques: list = field(default_factory=list)  # list[str] MITRE ATLAS technique IDs
