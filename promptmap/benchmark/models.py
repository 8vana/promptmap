from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BenchmarkProfile:
    profile_id: str
    version: str
    dataset_source: str
    objective_resolver: dict
    attack_ids: list[str]
    attack_overrides: dict[str, dict] = field(default_factory=dict)
    language: str = "en"
    scorer_policy: dict = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BenchmarkObjective:
    objective_id: str
    objective: str
    atlas_technique: str
    prompt_technique: str
    language_used: str
    is_fallback: bool
    ordinal: int
