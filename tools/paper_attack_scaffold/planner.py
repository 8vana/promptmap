from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from .common import normalize_attack_id
from .llm_client import LLMConfig, parse_json_response, run_prompt_sync
from .models import (
    AlgorithmStep,
    DivergenceRecord,
    EvidenceRecord,
    ImplementationPlan,
    PromptFragment,
)

_DEFAULT_EXCERPT_CHARS = 18000


@dataclass(frozen=True)
class PlannerConfig:
    attack_id: str | None = None
    display_name: str | None = None
    family: str | None = None
    paper_title: str | None = None
    paper_url: str | None = None
    provider: str | None = None
    model: str | None = None
    planner_backend: str = "auto"


@dataclass(frozen=True)
class PlannerOutcome:
    plan: ImplementationPlan
    planner_backend_used: str
    planner_excerpt: str
    raw_payload: dict[str, Any] | None = None
    raw_response_text: str = ""


def build_plan(
    *,
    config: PlannerConfig,
    paper_markdown: str,
    notes_text: str,
) -> PlannerOutcome:
    paper_title = config.paper_title or _infer_paper_title(paper_markdown)
    attack_id = normalize_attack_id(config.attack_id or _infer_attack_id(paper_title))
    display_name = config.display_name or _display_name_from_attack_id(attack_id)

    base_plan = _build_heuristic_plan(
        attack_id=attack_id,
        display_name=display_name,
        paper_title=paper_title,
        paper_url=config.paper_url or "",
        paper_markdown=paper_markdown,
        notes_text=notes_text,
        family_override=config.family,
    )

    backend_preference = config.planner_backend
    want_llm = backend_preference in {"auto", "llm"} and config.provider and config.model
    if want_llm:
        try:
            llm_config = LLMConfig(provider=config.provider, model=config.model)
            excerpt = _planner_excerpt(paper_markdown, notes_text)
            raw_response_text, llm_payload = _run_llm_planner(
                llm_config=llm_config,
                attack_id=attack_id,
                display_name=display_name,
                paper_title=paper_title,
                paper_url=config.paper_url or "",
                family_hint=config.family or "",
                paper_excerpt=excerpt,
                notes_text=notes_text,
            )
            plan = _merge_llm_payload(base_plan, llm_payload)
            return PlannerOutcome(
                plan=plan,
                planner_backend_used="llm",
                planner_excerpt=excerpt,
                raw_payload=llm_payload,
                raw_response_text=raw_response_text,
            )
        except Exception as exc:
            if backend_preference == "llm":
                raise
            base_plan.ambiguities.append(
                f"LLM planner fallback triggered after error: {type(exc).__name__}: {exc}"
            )

    excerpt = _planner_excerpt(paper_markdown, notes_text)
    return PlannerOutcome(
        plan=base_plan,
        planner_backend_used="heuristic",
        planner_excerpt=excerpt,
        raw_payload=None,
        raw_response_text="",
    )


def render_plan_markdown(plan: ImplementationPlan) -> str:
    parts: list[str] = []
    parts.append(f"# Implementation Plan: {plan.display_name}")
    parts.append("")
    parts.append("## Summary")
    parts.append("")
    parts.append(f"- `attack_id`: `{plan.attack_id}`")
    parts.append(f"- `paper_title`: {plan.paper_title or 'Unknown'}")
    parts.append(f"- `paper_url`: {plan.paper_url or 'Unknown'}")
    parts.append(f"- `family`: `{plan.family}`")
    parts.append(f"- `target_modes`: {', '.join(plan.target_modes) or 'none'}")
    parts.append(
        f"- `required_capabilities`: {', '.join(plan.required_capabilities) or 'none'}"
    )
    parts.append(
        f"- `supports_benchmark_recommendation`: `{str(plan.supports_benchmark_recommendation).lower()}`"
    )
    parts.append("")
    parts.append(plan.summary or "No summary generated.")
    parts.append("")
    parts.append("## Algorithm Steps")
    parts.append("")
    for step in plan.algorithm_steps:
        parts.append(f"### {step.step_id}. {step.title}")
        parts.append("")
        parts.append(step.description)
        parts.append("")
        parts.append(f"- `status`: `{step.status}`")
        parts.append(
            f"- `evidence_refs`: {', '.join(step.evidence_refs) if step.evidence_refs else 'none'}"
        )
        if step.notes:
            parts.append(f"- `notes`: {'; '.join(step.notes)}")
        parts.append("")
    parts.append("## Prompt Fragments")
    parts.append("")
    if plan.prompt_fragments:
        for fragment in plan.prompt_fragments:
            parts.append(f"### {fragment.name}")
            parts.append("")
            parts.append("```text")
            parts.append(fragment.text)
            parts.append("```")
            parts.append(
                f"Evidence: {', '.join(fragment.evidence_refs) if fragment.evidence_refs else 'none'}"
            )
            parts.append("")
    else:
        parts.append("No prompt fragments extracted.")
        parts.append("")
    parts.append("## Ambiguities")
    parts.append("")
    for ambiguity in plan.ambiguities or ["None recorded."]:
        parts.append(f"- {ambiguity}")
    parts.append("")
    parts.append("## Evidence")
    parts.append("")
    parts.append("### Paper Evidence")
    parts.append("")
    parts.extend(_render_evidence_block(plan.paper_evidence))
    parts.append("")
    parts.append("### Repo Evidence")
    parts.append("")
    parts.extend(_render_evidence_block(plan.repo_evidence))
    parts.append("")
    parts.append("### Operator Notes")
    parts.append("")
    parts.extend(_render_evidence_block(plan.operator_notes))
    parts.append("")
    if plan.divergences:
        parts.append("## Divergences")
        parts.append("")
        for divergence in plan.divergences:
            parts.append(f"- `{divergence.divergence_id}` `{divergence.topic}`")
            parts.append(f"  Paper: {divergence.paper_position}")
            parts.append(f"  Repo: {divergence.repo_position}")
            parts.append(f"  Decision: {divergence.planner_decision}")
            parts.append(f"  Severity: `{divergence.severity}`")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _render_evidence_block(records: list[EvidenceRecord]) -> list[str]:
    if not records:
        return ["No evidence recorded."]
    lines: list[str] = []
    for record in records:
        lines.append(f"- `{record.evidence_id}` `{record.source_kind}`")
        if record.section:
            lines.append(f"  Section: {record.section}")
        if record.locator:
            lines.append(f"  Locator: {record.locator}")
        if record.path:
            line_span = ""
            if record.line_start is not None:
                line_span = f":{record.line_start}"
                if record.line_end is not None and record.line_end != record.line_start:
                    line_span += f"-{record.line_end}"
            lines.append(f"  Path: {record.path}{line_span}")
        if record.quote_excerpt:
            lines.append(f"  Quote: {record.quote_excerpt}")
        if record.interpretation:
            lines.append(f"  Interpretation: {record.interpretation}")
        if record.note:
            lines.append(f"  Note: {record.note}")
    return lines


def _build_heuristic_plan(
    *,
    attack_id: str,
    display_name: str,
    paper_title: str,
    paper_url: str,
    paper_markdown: str,
    notes_text: str,
    family_override: str | None,
) -> ImplementationPlan:
    paper_evidence = _extract_paper_evidence(paper_markdown)
    operator_notes = _extract_operator_notes(notes_text)
    family = family_override or _infer_family(paper_markdown, paper_title)
    target_modes = _infer_target_modes(family)
    required_capabilities = _infer_required_capabilities(family)
    default_params = _infer_default_params(family)
    evidence_refs = [record.evidence_id for record in paper_evidence[:2]]
    if operator_notes:
        evidence_refs.append(operator_notes[0].evidence_id)
    algorithm_steps = _default_algorithm_steps(family, evidence_refs)
    prompt_fragments = _extract_prompt_fragments(paper_markdown, evidence_refs)
    ambiguities = [
        "Planner MVP generated this draft heuristically; validate the attack flow against the paper.",
        "Default parameters are provisional unless the paper states them explicitly.",
    ]
    if not paper_url:
        ambiguities.append("Paper URL was not supplied and could not be verified.")
    summary = (
        "Heuristic planner summary based on normalized paper text. "
        "This draft is intended for human review before any code generation or promotion."
    )
    return ImplementationPlan(
        attack_id=attack_id,
        display_name=display_name,
        paper_title=paper_title,
        paper_url=paper_url,
        family=family,
        target_modes=target_modes,
        required_capabilities=required_capabilities,
        supports_benchmark_recommendation=False,
        default_params=default_params,
        summary=summary,
        algorithm_steps=algorithm_steps,
        prompt_fragments=prompt_fragments,
        ambiguities=ambiguities,
        paper_evidence=paper_evidence,
        repo_evidence=[],
        operator_notes=operator_notes,
        divergences=[],
    )


def _extract_paper_evidence(markdown: str) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    sections = _parse_markdown_sections(markdown)
    if sections:
        title = sections[0]["heading"]
        records.append(
            EvidenceRecord(
                evidence_id="paper:title:1",
                source_kind="paper",
                section="title",
                locator="top",
                quote_excerpt=title,
                interpretation="Paper title extracted from the first heading.",
                confidence="high",
            )
        )
        preferred_tokens = ("abstract", "3.1", "3.2", "3.3", "4.1", "appendix")
        selected: list[dict[str, str]] = []
        for token in preferred_tokens:
            match = next(
                (
                    section for section in sections
                    if section["heading"].lower().startswith(token)
                ),
                None,
            )
            if match and match not in selected:
                selected.append(match)
        for section in sections:
            if len(selected) >= 6:
                break
            if (
                section not in selected
                and section["heading"].lower() not in {"title", title.lower()}
                and _section_is_useful_for_evidence(section["heading"])
            ):
                selected.append(section)
        for idx, section in enumerate(selected, start=1):
            heading = section["heading"]
            excerpt = section["content"][:320] if section["content"] else heading
            records.append(
                EvidenceRecord(
                    evidence_id=f"paper:section:{_section_slug(heading)}",
                    source_kind="paper",
                    section=heading,
                    locator=f"heading:{heading}",
                    quote_excerpt=excerpt,
                    interpretation="Section excerpt captured during normalization.",
                    confidence="high" if heading.lower().startswith(("abstract", "3.2", "3.3")) else "medium",
                )
            )
        records.extend(_extract_special_paper_evidence(markdown, sections))
    if not records:
        records.append(
            EvidenceRecord(
                evidence_id="paper:excerpt:1",
                source_kind="paper",
                section="body",
                locator="top",
                quote_excerpt=markdown[:280],
                interpretation="Fallback excerpt from paper body.",
                confidence="low",
            )
        )
    return records


def _extract_special_paper_evidence(
    markdown: str, sections: list[dict[str, str]]
) -> list[EvidenceRecord]:
    records: list[EvidenceRecord] = []
    seen_ids: set[str] = set()

    for raw_line in markdown.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        figure_match = re.match(r"Figure\s+(\d+):\s*(.+)", line, flags=re.IGNORECASE)
        if figure_match:
            figure_no = figure_match.group(1)
            evidence_id = f"paper:figure:{figure_no}"
            if evidence_id not in seen_ids:
                seen_ids.add(evidence_id)
                records.append(
                    EvidenceRecord(
                        evidence_id=evidence_id,
                        source_kind="paper",
                        section=f"Figure {figure_no}",
                        locator=f"figure:{figure_no}",
                        quote_excerpt=line[:320],
                        interpretation="Figure caption extracted from normalized markdown.",
                        confidence="medium",
                    )
                )
            continue

        appendix_match = re.search(r"\b(?:app\.|appendix)\s*([a-z])\b", line, flags=re.IGNORECASE)
        if appendix_match:
            appendix_label = appendix_match.group(1).upper()
            evidence_id = f"paper:appendix_ref:{appendix_label.lower()}"
            if evidence_id not in seen_ids:
                seen_ids.add(evidence_id)
                records.append(
                    EvidenceRecord(
                        evidence_id=evidence_id,
                        source_kind="paper",
                        section=f"Appendix {appendix_label} reference",
                        locator=f"appendix-ref:{appendix_label}",
                        quote_excerpt=line[:320],
                        interpretation="Inline appendix reference captured from paper body.",
                        confidence="medium",
                    )
                )

        footnote_match = re.match(r"^(\d+)\s+(https?://\S+.*|[A-Z].{20,})$", line)
        if footnote_match:
            footnote_no = footnote_match.group(1)
            evidence_id = f"paper:footnote:{footnote_no}"
            if evidence_id not in seen_ids:
                seen_ids.add(evidence_id)
                records.append(
                    EvidenceRecord(
                        evidence_id=evidence_id,
                        source_kind="paper",
                        section=f"Footnote {footnote_no}",
                        locator=f"footnote:{footnote_no}",
                        quote_excerpt=line[:320],
                        interpretation="Footnote line extracted from normalized markdown.",
                        confidence="medium",
                    )
                )

    formula_count = markdown.count("<!-- formula-not-decoded -->")
    if formula_count:
        formula_context = next(
            (
                section
                for section in sections
                if section["heading"].lower().startswith("3.2")
            ),
            None,
        )
        formula_excerpt = ""
        if formula_context:
            formula_excerpt = formula_context["content"][:320]
        if not formula_excerpt:
            formula_excerpt = "Mathematical formulas were present in the normalized paper but were not decoded."
        records.append(
            EvidenceRecord(
                evidence_id="paper:formula:3_2",
                source_kind="paper",
                section="3.2 formulas",
                locator="section:3.2 formulas",
                quote_excerpt=formula_excerpt,
                interpretation=(
                    f"Detected {formula_count} formula placeholder blocks in the normalized paper."
                ),
                confidence="medium",
            )
        )

    return records


def _extract_operator_notes(notes_text: str) -> list[EvidenceRecord]:
    if not notes_text.strip():
        return []
    return [
        EvidenceRecord(
            evidence_id="note:1",
            source_kind="operator_note",
            note=notes_text[:600],
            interpretation="Operator-supplied note included during planning.",
            confidence="medium",
        )
    ]


def _infer_attack_id(paper_title: str) -> str:
    if not paper_title:
        return "paper_attack"
    head = paper_title.split(":")[0].strip()
    return normalize_attack_id(head or "paper_attack")


def _display_name_from_attack_id(attack_id: str) -> str:
    return " ".join(part.upper() if len(part) <= 3 else part.capitalize() for part in attack_id.split("_")) + " Attack"


def _infer_paper_title(markdown: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip()
        return stripped[:180]
    return ""


def _infer_family(markdown: str, paper_title: str) -> str:
    lowered = f"{paper_title}\n{markdown}".lower()
    if any(
        token in lowered
        for token in (
            "strategically splice",
            "semantically coherent attack prompt",
            "splice identified real-world instructions",
            "embedding the malicious instruction at the end",
        )
    ):
        return "single_turn"
    if any(
        token in lowered
        for token in (
            "multi-turn",
            "iterative",
            "across turns",
            "conversation state",
            "subsequent rounds",
            "self-interaction",
        )
    ):
        return "multi_turn"
    if "agent" in lowered or "autonomous" in lowered or "orchestr" in lowered:
        return "autonomous"
    return "single_turn"


def _infer_target_modes(family: str) -> list[str]:
    if family == "single_turn":
        return ["api", "stateless"]
    if family == "multi_turn":
        return ["api", "stateful"]
    return ["api", "stateful"]


def _infer_required_capabilities(family: str) -> list[str]:
    if family == "single_turn":
        return ["scorer_llm"]
    if family == "multi_turn":
        return ["scorer_llm", "adversarial_llm"]
    return ["scorer_llm", "adversarial_llm"]


def _infer_default_params(family: str) -> dict[str, Any]:
    if family == "single_turn":
        return {"seed_prompt": ""}
    if family == "multi_turn":
        return {"max_iterations": 10}
    return {"max_iterations": 10}


def _default_algorithm_steps(family: str, evidence_refs: list[str]) -> list[AlgorithmStep]:
    if family == "multi_turn":
        return [
            AlgorithmStep(
                step_id="S1",
                title="Construct initial framing",
                description="Build the initial jailbreak prompt or wrapper around the objective.",
                evidence_refs=list(evidence_refs),
            ),
            AlgorithmStep(
                step_id="S2",
                title="Query target iteratively",
                description="Send the attack prompt, inspect the answer, and maintain conversation state.",
                evidence_refs=list(evidence_refs),
            ),
            AlgorithmStep(
                step_id="S3",
                title="Refine based on target feedback",
                description="Adjust wording or strategy across turns until the paper-defined stopping condition is reached.",
                evidence_refs=list(evidence_refs),
                notes=["Stopping condition may require paper-specific review."],
            ),
        ]
    if family == "autonomous":
        return [
            AlgorithmStep(
                step_id="S1",
                title="Select attack primitive",
                description="Choose the prompt strategy or action sequence implied by the paper.",
                evidence_refs=list(evidence_refs),
            ),
            AlgorithmStep(
                step_id="S2",
                title="Execute and adapt",
                description="Run the selected strategy and adapt based on intermediate feedback.",
                evidence_refs=list(evidence_refs),
            ),
            AlgorithmStep(
                step_id="S3",
                title="Evaluate completion",
                description="Score the output and decide whether the autonomous loop should stop.",
                evidence_refs=list(evidence_refs),
            ),
        ]
    return [
        AlgorithmStep(
            step_id="S1",
            title="Construct single-turn framing",
            description="Wrap the objective in the attack-specific framing described by the paper.",
            evidence_refs=list(evidence_refs),
        ),
        AlgorithmStep(
            step_id="S2",
            title="Send the prompt once",
            description="Issue the constructed prompt to the target without additional turns.",
            evidence_refs=list(evidence_refs),
        ),
        AlgorithmStep(
            step_id="S3",
            title="Score the response",
            description="Evaluate whether the response achieved the original objective.",
            evidence_refs=list(evidence_refs),
        ),
    ]


def _extract_prompt_fragments(markdown: str, evidence_refs: list[str]) -> list[PromptFragment]:
    lines = [line.strip() for line in markdown.splitlines() if line.strip()]
    snippets: list[str] = []
    for line in lines:
        lowered = line.lower()
        if any(token in lowered for token in ("prompt", "instruction", "template", "roleplay", "role-play")):
            snippets.append(line[:320])
        if len(snippets) >= 2:
            break
    if not snippets:
        return []
    return [
        PromptFragment(
            name=f"fragment_{idx + 1}",
            text=snippet,
            evidence_refs=list(evidence_refs[:1]),
        )
        for idx, snippet in enumerate(snippets)
    ]


def _planner_excerpt(markdown: str, notes_text: str) -> str:
    chunks = [markdown[:_DEFAULT_EXCERPT_CHARS]]
    if notes_text.strip():
        chunks.append("\n\n## Operator Notes\n" + notes_text[:2000])
    return "".join(chunks)


def _run_llm_planner(
    *,
    llm_config: LLMConfig,
    attack_id: str,
    display_name: str,
    paper_title: str,
    paper_url: str,
    family_hint: str,
    paper_excerpt: str,
    notes_text: str,
) -> tuple[str, dict[str, Any]]:
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    system_prompt = (prompts_dir / "planner_system.txt").read_text(encoding="utf-8")
    user_template = (prompts_dir / "planner_user.txt").read_text(encoding="utf-8")
    user_prompt = user_template.format(
        attack_id=attack_id,
        display_name=display_name,
        paper_title=paper_title,
        paper_url=paper_url,
        family_hint=family_hint or "unknown",
        paper_excerpt=paper_excerpt,
        notes_text=notes_text or "None",
    )
    raw = run_prompt_sync(llm_config, system_prompt=system_prompt, user_prompt=user_prompt)
    return raw, parse_json_response(raw)


def _merge_llm_payload(base_plan: ImplementationPlan, payload: dict[str, Any]) -> ImplementationPlan:
    family = _normalize_family(
        payload.get("family"),
        base_plan.family,
        summary=str(payload.get("summary") or ""),
        payload=payload,
    )
    target_modes = _normalize_target_modes(
        _clean_string_list(payload.get("target_modes")),
        family=family,
        fallback=base_plan.target_modes,
    )
    required_capabilities = _normalize_required_capabilities(
        _clean_string_list(payload.get("required_capabilities")),
        family=family,
        fallback=base_plan.required_capabilities,
    )
    summary = str(payload.get("summary") or base_plan.summary)
    default_params = payload.get("default_params") if isinstance(payload.get("default_params"), dict) else base_plan.default_params
    supports = False
    ambiguities = [*base_plan.ambiguities, *_clean_string_list(payload.get("ambiguities"))]
    if payload.get("supports_benchmark_recommendation") is True:
        ambiguities.append(
            "Benchmark recommendation was normalized to false in Phase A pending explicit human review."
        )
    divergences = [*base_plan.divergences, *_parse_divergences(payload.get("divergences"))]

    evidence_refs = [record.evidence_id for record in base_plan.paper_evidence[:2]]
    if base_plan.operator_notes:
        evidence_refs.append(base_plan.operator_notes[0].evidence_id)
    steps = _parse_steps(
        payload.get("algorithm_steps"),
        evidence_refs,
        paper_evidence=base_plan.paper_evidence,
        ambiguities=ambiguities,
    ) or base_plan.algorithm_steps
    fragments = _parse_fragments(
        payload.get("prompt_fragments"),
        evidence_refs,
        paper_evidence=base_plan.paper_evidence,
        ambiguities=ambiguities,
    ) or base_plan.prompt_fragments

    return ImplementationPlan(
        attack_id=base_plan.attack_id,
        display_name=base_plan.display_name,
        paper_title=base_plan.paper_title,
        paper_url=base_plan.paper_url,
        family=family,
        target_modes=target_modes,
        required_capabilities=required_capabilities,
        supports_benchmark_recommendation=supports,
        default_params=default_params,
        summary=summary,
        algorithm_steps=steps,
        prompt_fragments=fragments,
        ambiguities=_dedupe_preserve(ambiguities),
        paper_evidence=base_plan.paper_evidence,
        repo_evidence=base_plan.repo_evidence,
        operator_notes=base_plan.operator_notes,
        divergences=divergences,
    )

def _parse_steps(
    raw: Any,
    default_evidence_refs: list[str],
    *,
    paper_evidence: list[EvidenceRecord],
    ambiguities: list[str],
) -> list[AlgorithmStep]:
    if not isinstance(raw, list):
        return []
    steps: list[AlgorithmStep] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()
        description = str(item.get("description", "")).strip()
        if not title or not description:
            continue
        refs = _normalize_evidence_refs(
            _clean_string_list(item.get("evidence_refs")),
            default_evidence_refs=default_evidence_refs,
            paper_evidence=paper_evidence,
            ambiguities=ambiguities,
        )
        steps.append(
            AlgorithmStep(
                step_id=str(item.get("step_id") or f"S{idx}"),
                title=title,
                description=description,
                evidence_refs=refs,
                status=_normalize_status(str(item.get("status") or "supported")),
                notes=_clean_string_list(item.get("notes")),
            )
        )
    return steps


def _parse_fragments(
    raw: Any,
    default_evidence_refs: list[str],
    *,
    paper_evidence: list[EvidenceRecord],
    ambiguities: list[str],
) -> list[PromptFragment]:
    if not isinstance(raw, list):
        return []
    fragments: list[PromptFragment] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "")).strip()
        if not text:
            continue
        fragments.append(
            PromptFragment(
                name=str(item.get("name") or f"fragment_{idx}"),
                text=text,
                evidence_refs=_normalize_evidence_refs(
                    _clean_string_list(item.get("evidence_refs")),
                    default_evidence_refs=list(default_evidence_refs[:1]),
                    paper_evidence=paper_evidence,
                    ambiguities=ambiguities,
                ),
            )
        )
    return fragments


def _parse_divergences(raw: Any) -> list[DivergenceRecord]:
    if not isinstance(raw, list):
        return []
    divergences: list[DivergenceRecord] = []
    for idx, item in enumerate(raw, start=1):
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic", "")).strip()
        decision = str(item.get("planner_decision", "")).strip()
        if not topic or not decision:
            continue
        divergences.append(
            DivergenceRecord(
                divergence_id=str(item.get("divergence_id") or f"D{idx}"),
                topic=topic,
                paper_position=str(item.get("paper_position") or "not specified"),
                repo_position=str(item.get("repo_position") or "not specified"),
                planner_decision=decision,
                severity=str(item.get("severity") or "medium"),
            )
        )
    return divergences


def _clean_string_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _dedupe_preserve(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _normalize_family(raw_family: Any, fallback: str, *, summary: str, payload: dict[str, Any]) -> str:
    value = str(raw_family or "").strip().lower()
    if value in {"single_turn", "multi_turn", "autonomous"}:
        return value
    text = " ".join(
        [
            value,
            summary.lower(),
            " ".join(str(step.get("description", "")) for step in payload.get("algorithm_steps", []) if isinstance(step, dict)).lower(),
        ]
    )
    if any(
        token in text
        for token in (
            "strategically splice",
            "splice selected real-world instructions",
            "around malicious instruction",
            "attack prompt",
        )
    ):
        return "single_turn"
    if any(token in text for token in ("multi-turn", "iterative", "across turns", "conversation state")):
        return "multi_turn"
    if any(token in text for token in ("autonomous", "agent", "orchestr")):
        return "autonomous"
    return fallback


def _normalize_target_modes(raw_modes: list[str], *, family: str, fallback: list[str]) -> list[str]:
    allowed = {"api", "browser", "stateless", "stateful"}
    mapped: list[str] = []
    for mode in raw_modes:
        lowered = mode.lower()
        if lowered in allowed:
            mapped.append(lowered)
            continue
        if lowered in {"chat", "instruction_following", "instruction-following", "llm"}:
            mapped.extend(["api", "stateful"] if family != "single_turn" else ["api", "stateless"])
        elif lowered in {"web", "ui"}:
            mapped.append("browser")
    mapped = _dedupe_preserve(mapped)
    return mapped or list(fallback)


def _normalize_required_capabilities(raw_caps: list[str], *, family: str, fallback: list[str]) -> list[str]:
    allowed = {"scorer_llm", "adversarial_llm", "tool_calling"}
    mapped: list[str] = []
    for capability in raw_caps:
        lowered = capability.lower()
        if lowered in allowed:
            mapped.append(lowered)
            continue
        if lowered in {"probability_calculation", "instruction_ranking", "prompt_construction", "prompt_splicing"}:
            continue
    mapped = _dedupe_preserve(mapped)
    if mapped:
        return mapped
    return _infer_required_capabilities(family) or list(fallback)


def _normalize_status(raw_status: str) -> str:
    value = raw_status.strip().lower()
    if value in {"supported", "well_defined", "well-defined", "specified"}:
        return "supported"
    if value in {"ambiguous", "partial", "partially_supported"}:
        return "ambiguous"
    return "supported"


def _normalize_evidence_refs(
    raw_refs: list[str],
    *,
    default_evidence_refs: list[str],
    paper_evidence: list[EvidenceRecord],
    ambiguities: list[str],
) -> list[str]:
    if not raw_refs:
        return list(default_evidence_refs)
    resolved: list[str] = []
    for ref in raw_refs:
        if any(record.evidence_id == ref for record in paper_evidence):
            resolved.append(ref)
            continue
        match = _resolve_evidence_ref(ref, paper_evidence)
        if match:
            resolved.append(match)
        else:
            ambiguities.append(
                f"Could not resolve planner evidence reference '{ref}' to a stored evidence record."
            )
    resolved = _dedupe_preserve(resolved)
    return resolved or list(default_evidence_refs)


def _resolve_evidence_ref(ref: str, records: list[EvidenceRecord]) -> str | None:
    lowered = ref.strip().lower()
    section_number = ""
    if lowered.startswith("section "):
        section_number = lowered.replace("section ", "", 1).strip()
    elif lowered.startswith("appendix "):
        section_number = lowered
    footnote_match = re.search(r"\bfootnote\s*(\d+)\b", lowered)
    if footnote_match:
        target = next(
            (
                record
                for record in records
                if record.evidence_id == f"paper:footnote:{footnote_match.group(1)}"
                or record.locator == f"footnote:{footnote_match.group(1)}"
            ),
            None,
        )
        if target:
            return target.evidence_id
    figure_match = re.search(r"\b(?:figure|fig\.)\s*(\d+)\b", lowered)
    if figure_match:
        target = next(
            (
                record for record in records
                if record.evidence_id == f"paper:figure:{figure_match.group(1)}"
                or record.locator == f"figure:{figure_match.group(1)}"
            ),
            None,
        )
        if target:
            return target.evidence_id
    appendix_match = re.search(r"\b(?:app\.|appendix)\s*([a-z])\b", lowered)
    if appendix_match:
        appendix_label = appendix_match.group(1).lower()
        target = next(
            (
                record for record in records
                if record.evidence_id == f"paper:appendix_ref:{appendix_label}"
                or record.locator.lower() == f"appendix-ref:{appendix_label.upper()}"
            ),
            None,
        )
        if target:
            return target.evidence_id
    if "formula" in lowered:
        target = next(
            (
                record for record in records
                if record.evidence_id.startswith("paper:formula:")
                or "formula" in record.section.lower()
            ),
            None,
        )
        if target:
            return target.evidence_id
        target = next((record for record in records if record.section.lower().startswith("3.2")), None)
        if target:
            return target.evidence_id
    if "equation" in lowered:
        target = next(
            (
                record for record in records
                if record.evidence_id.startswith("paper:formula:")
                or "formula" in record.section.lower()
            ),
            None,
        )
        if target:
            return target.evidence_id
    if section_number:
        target = next(
            (
                record for record in records
                if record.section.lower().startswith(section_number)
                or record.section.lower().startswith(f"{section_number} ")
                or lowered in record.section.lower()
            ),
            None,
        )
        if target:
            return target.evidence_id
    target = next(
        (
            record for record in records
            if lowered in record.section.lower() or lowered in record.quote_excerpt.lower()
        ),
        None,
    )
    return target.evidence_id if target else None


def _parse_markdown_sections(markdown: str) -> list[dict[str, str]]:
    sections: list[dict[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    for raw in markdown.splitlines():
        line = raw.rstrip()
        if line.startswith("#"):
            if current_heading:
                sections.append(
                    {
                        "heading": current_heading,
                        "content": " ".join(current_lines).strip(),
                    }
                )
            current_heading = line.lstrip("#").strip()
            current_lines = []
            continue
        if not current_heading or not line.strip():
            continue
        if line.startswith("<!--") or line.startswith("Figure ") or line.startswith("Table "):
            continue
        current_lines.append(line.strip())
    if current_heading:
        sections.append(
            {
                "heading": current_heading,
                "content": " ".join(current_lines).strip(),
            }
        )
    return sections


def _section_slug(heading: str) -> str:
    lowered = heading.lower().strip()
    if lowered.startswith("appendix"):
        return lowered.replace(" ", "_")
    first_token = lowered.split(" ", 1)[0]
    return first_token.replace(".", "_")


def _section_is_useful_for_evidence(heading: str) -> bool:
    lowered = heading.lower().strip()
    if lowered == "abstract" or lowered.startswith("appendix"):
        return True
    first = lowered.split(" ", 1)[0]
    return first[:1].isdigit()
