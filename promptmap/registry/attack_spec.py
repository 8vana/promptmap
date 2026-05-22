from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AttackSpec:
    attack_id: str
    import_path: str
    registered_name: str
    display_name: str
    family: str
    description: str
    source_type: str
    paper_title: str = ""
    paper_url: str = ""
    paper_year: int | None = None
    prompt_technique_aware: bool = False
    supports_benchmark: bool = True
    target_modes: list[str] = field(default_factory=list)
    required_capabilities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    default_params: dict = field(default_factory=dict)
    benchmark_defaults: dict = field(default_factory=dict)
    compatible_atlas_techniques: list[str] = field(default_factory=list)
