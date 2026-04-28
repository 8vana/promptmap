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
