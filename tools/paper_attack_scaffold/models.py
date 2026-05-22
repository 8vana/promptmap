from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvidenceRecord:
    evidence_id: str
    source_kind: str
    section: str = ""
    locator: str = ""
    quote_excerpt: str = ""
    interpretation: str = ""
    confidence: str = "medium"
    repo_url: str = ""
    path: str = ""
    line_start: int | None = None
    line_end: int | None = None
    paper_aligned: str = "unknown"
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "evidence_id": self.evidence_id,
            "source_kind": self.source_kind,
            "confidence": self.confidence,
        }
        optional = {
            "section": self.section,
            "locator": self.locator,
            "quote_excerpt": self.quote_excerpt,
            "interpretation": self.interpretation,
            "repo_url": self.repo_url,
            "path": self.path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "paper_aligned": self.paper_aligned,
            "note": self.note,
        }
        for key, value in optional.items():
            if value not in ("", None):
                data[key] = value
        return data


@dataclass
class AlgorithmStep:
    step_id: str
    title: str
    description: str
    evidence_refs: list[str] = field(default_factory=list)
    status: str = "supported"
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "title": self.title,
            "description": self.description,
            "evidence_refs": list(self.evidence_refs),
            "status": self.status,
            "notes": list(self.notes),
        }


@dataclass
class PromptFragment:
    name: str
    text: str
    evidence_refs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "text": self.text,
            "evidence_refs": list(self.evidence_refs),
        }


@dataclass
class DivergenceRecord:
    divergence_id: str
    topic: str
    paper_position: str
    repo_position: str
    planner_decision: str
    severity: str = "medium"

    def to_dict(self) -> dict[str, Any]:
        return {
            "divergence_id": self.divergence_id,
            "topic": self.topic,
            "paper_position": self.paper_position,
            "repo_position": self.repo_position,
            "planner_decision": self.planner_decision,
            "severity": self.severity,
        }


@dataclass
class ImplementationPlan:
    attack_id: str
    display_name: str
    paper_title: str
    paper_url: str
    family: str
    target_modes: list[str]
    required_capabilities: list[str]
    supports_benchmark_recommendation: bool
    default_params: dict[str, Any] = field(default_factory=dict)
    source_of_truth_priority: list[str] = field(
        default_factory=lambda: ["paper", "operator_notes", "reference_repo"]
    )
    summary: str = ""
    algorithm_steps: list[AlgorithmStep] = field(default_factory=list)
    prompt_fragments: list[PromptFragment] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    paper_evidence: list[EvidenceRecord] = field(default_factory=list)
    repo_evidence: list[EvidenceRecord] = field(default_factory=list)
    operator_notes: list[EvidenceRecord] = field(default_factory=list)
    divergences: list[DivergenceRecord] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attack_id": self.attack_id,
            "display_name": self.display_name,
            "paper_title": self.paper_title,
            "paper_url": self.paper_url,
            "family": self.family,
            "target_modes": list(self.target_modes),
            "required_capabilities": list(self.required_capabilities),
            "supports_benchmark_recommendation": self.supports_benchmark_recommendation,
            "source_of_truth_priority": list(self.source_of_truth_priority),
            "default_params": dict(self.default_params),
            "summary": self.summary,
            "evidence_summary": {
                "paper_evidence_count": len(self.paper_evidence),
                "repo_evidence_count": len(self.repo_evidence),
                "operator_note_count": len(self.operator_notes),
            },
            "algorithm_steps": [step.to_dict() for step in self.algorithm_steps],
            "prompt_fragments": [fragment.to_dict() for fragment in self.prompt_fragments],
            "ambiguities": list(self.ambiguities),
            "paper_evidence": [record.to_dict() for record in self.paper_evidence],
            "repo_evidence": [record.to_dict() for record in self.repo_evidence],
            "operator_notes": [record.to_dict() for record in self.operator_notes],
            "divergences": [record.to_dict() for record in self.divergences],
        }
