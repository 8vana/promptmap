from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import py_compile
from typing import Any

import yaml


@dataclass(frozen=True)
class AuditConfig:
    attack_id: str
    staging_dir: Path


@dataclass(frozen=True)
class AuditOutcome:
    coverage_report_text: str
    audit_verdict: dict[str, Any]
    review_checklist_text: str


def run_audit(config: AuditConfig) -> AuditOutcome:
    plan_path = config.staging_dir / "implementation_plan.json"
    module_path = config.staging_dir / "attack_module.py"
    catalog_path = config.staging_dir / "attack_catalog.yaml"

    if not plan_path.exists():
        raise ValueError(f"Missing implementation plan: {plan_path}")
    if not module_path.exists():
        raise ValueError(f"Missing generated attack module: {module_path}")
    if not catalog_path.exists():
        raise ValueError(f"Missing generated attack catalog: {catalog_path}")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    module_source = module_path.read_text(encoding="utf-8")
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}

    module_runtime_source = _runtime_source(module_source)
    py_compile_ok, py_compile_error = _check_py_compile(module_path)
    generic_baseline_detected = "forge draft executing plan-driven baseline flow" in module_source

    step_results = [
        _audit_step(step, module_runtime_source, generic_baseline_detected)
        for step in plan.get("algorithm_steps", [])
        if isinstance(step, dict)
    ]

    categories: list[str] = []
    recommended_actions: list[str] = []

    missing_steps = [step for step in step_results if step["status"] == "missing"]
    partial_steps = [step for step in step_results if step["status"] == "partial"]

    if missing_steps:
        categories.append("missing_algorithm_steps")
        recommended_actions.append(
            "Implement the missing algorithm steps in attack_module.py before promotion."
        )
    if generic_baseline_detected:
        categories.append("unsafe_inference_detected")
        recommended_actions.append(
            "Replace the generic forge baseline with paper-specific prompt construction and control flow."
        )
    if not _catalog_supports_benchmark(catalog):
        categories.append("benchmark_not_advised")
        recommended_actions.append(
            "Keep supports_benchmark disabled until the implementation is paper-faithful and tested."
        )

    catalog_checks = _audit_catalog(plan, catalog)
    if catalog_checks["mismatches"]:
        recommended_actions.append(
            "Resolve catalog mismatches so runtime metadata stays aligned with the implementation plan."
        )

    if not py_compile_ok:
        verdict = "blocked_by_missing_information"
        recommended_actions.append("Fix Python syntax/import issues before continuing.")
    elif missing_steps or generic_baseline_detected:
        verdict = "needs_refinement"
    else:
        verdict = "pass_with_review"

    audit_verdict = {
        "attack_id": plan.get("attack_id") or config.attack_id,
        "verdict": verdict,
        "categories": categories,
        "module_checks": {
            "py_compile_ok": py_compile_ok,
            "py_compile_error": py_compile_error,
            "generic_baseline_detected": generic_baseline_detected,
        },
        "catalog_checks": catalog_checks,
        "step_coverage": {
            "implemented": [step["step_id"] for step in step_results if step["status"] == "implemented"],
            "partial": [step["step_id"] for step in step_results if step["status"] == "partial"],
            "missing": [step["step_id"] for step in step_results if step["status"] == "missing"],
        },
        "recommended_next_actions": recommended_actions,
    }

    coverage_report_text = _render_coverage_report(
        plan=plan,
        step_results=step_results,
        verdict=audit_verdict,
    )
    review_checklist_text = _render_review_checklist(
        plan=plan,
        verdict=audit_verdict,
        step_results=step_results,
        catalog_checks=catalog_checks,
    )

    return AuditOutcome(
        coverage_report_text=coverage_report_text,
        audit_verdict=audit_verdict,
        review_checklist_text=review_checklist_text,
    )


def _runtime_source(module_source: str) -> str:
    marker = "\nclass "
    _, sep, tail = module_source.partition(marker)
    if not sep:
        return module_source
    return "class " + tail


def _check_py_compile(module_path: Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(module_path), doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)


def _audit_step(step: dict[str, Any], runtime_source: str, generic_baseline_detected: bool) -> dict[str, str]:
    step_id = str(step.get("step_id") or "").strip()
    title = str(step.get("title") or "").strip()
    lowered = step_id.lower()
    source_lower = runtime_source.lower()

    status = "missing"
    reason = "No implementation signal detected for this plan step."

    if lowered == "splice_instructions":
        if "instruction_prefixes" in source_lower and "instruction_suffixes" in source_lower:
            status = "partial" if generic_baseline_detected else "implemented"
            reason = "The draft supports prefix/suffix splicing, but still uses a generic baseline flow."
    elif lowered == "construct_responses":
        if "prompt_fragments" in source_lower or "affirmation_response_example" in source_lower:
            status = "partial"
            reason = "Response examples are preserved as metadata, but response-set construction is not executable."
    elif lowered == "collect_instructions":
        if any(token in source_lower for token in ("alpaca", "load_dataset", "real_world_instructions")):
            status = "partial"
            reason = "Dataset terminology is present, but no collection/loading pipeline is implemented."
    elif lowered in {"calculate_probabilities", "calculate_response_tendencies"}:
        if any(token in source_lower for token in ("logprob", "probability", "token_probability", "affirmation tendency")):
            status = "partial"
            reason = "Probability-related logic is referenced, but the actual computation path is not implemented."
    elif lowered in {"score_instructions", "rank_instructions", "select_top_instructions", "filter_instructions"}:
        if lowered in source_lower:
            status = "partial"
            reason = "The step is mentioned in metadata, but the runtime code does not execute the step."

    if status == "missing" and lowered in source_lower:
        status = "partial"
        reason = "The step identifier appears in the draft metadata, but there is no step-specific runtime logic."

    return {
        "step_id": step_id,
        "title": title,
        "status": status,
        "reason": reason,
    }


def _catalog_supports_benchmark(catalog: dict[str, Any]) -> bool:
    return bool(catalog.get("supports_benchmark"))


def _audit_catalog(plan: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    mismatches: list[str] = []
    if catalog.get("attack_id") != plan.get("attack_id"):
        mismatches.append("attack_id")
    if catalog.get("family") != plan.get("family"):
        mismatches.append("family")
    if catalog.get("display_name") != plan.get("display_name"):
        mismatches.append("display_name")
    if catalog.get("paper_title") != plan.get("paper_title"):
        mismatches.append("paper_title")
    if catalog.get("paper_url") != plan.get("paper_url"):
        mismatches.append("paper_url")
    return {
        "mismatches": mismatches,
        "supports_benchmark": bool(catalog.get("supports_benchmark")),
        "source_type": str(catalog.get("source_type") or ""),
    }


def _render_coverage_report(
    *,
    plan: dict[str, Any],
    step_results: list[dict[str, str]],
    verdict: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# Coverage Report: {plan.get('display_name') or plan.get('attack_id')}")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"- `verdict`: `{verdict['verdict']}`")
    lines.append(
        f"- `categories`: {', '.join(verdict['categories']) if verdict['categories'] else 'none'}"
    )
    lines.append("")
    lines.append("## Step Coverage")
    lines.append("")
    for step in step_results:
        lines.append(f"### {step['step_id']}: {step['title']}")
        lines.append("")
        lines.append(f"- `status`: `{step['status']}`")
        lines.append(f"- {step['reason']}")
        lines.append("")
    lines.append("## Module Checks")
    lines.append("")
    lines.append(f"- `py_compile_ok`: `{str(verdict['module_checks']['py_compile_ok']).lower()}`")
    lines.append(
        f"- `generic_baseline_detected`: `{str(verdict['module_checks']['generic_baseline_detected']).lower()}`"
    )
    if verdict["module_checks"]["py_compile_error"]:
        lines.append(f"- `py_compile_error`: {verdict['module_checks']['py_compile_error']}")
    lines.append("")
    lines.append("## Catalog Checks")
    lines.append("")
    lines.append(
        f"- `supports_benchmark`: `{str(verdict['catalog_checks']['supports_benchmark']).lower()}`"
    )
    lines.append(f"- `source_type`: `{verdict['catalog_checks']['source_type']}`")
    lines.append(
        f"- `mismatches`: {', '.join(verdict['catalog_checks']['mismatches']) if verdict['catalog_checks']['mismatches'] else 'none'}"
    )
    lines.append("")
    lines.append("## Recommended Actions")
    lines.append("")
    for action in verdict["recommended_next_actions"] or ["No additional actions recorded."]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)


def _render_review_checklist(
    *,
    plan: dict[str, Any],
    verdict: dict[str, Any],
    step_results: list[dict[str, str]],
    catalog_checks: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append(f"# Review Checklist: {plan.get('display_name') or plan.get('attack_id')}")
    lines.append("")
    lines.append("## Audit Summary")
    lines.append("")
    lines.append(f"- `verdict`: `{verdict['verdict']}`")
    lines.append(
        f"- `categories`: {', '.join(verdict['categories']) if verdict['categories'] else 'none'}"
    )
    lines.append("")
    lines.append("## Remaining Work")
    lines.append("")
    for step in step_results:
        if step["status"] == "implemented":
            continue
        lines.append(f"- `{step['step_id']}` is `{step['status']}`: {step['reason']}")
    if catalog_checks["mismatches"]:
        lines.append(
            f"- Resolve catalog mismatches: {', '.join(catalog_checks['mismatches'])}"
        )
    if not catalog_checks["supports_benchmark"]:
        lines.append("- Keep `supports_benchmark: false` until the audit findings are resolved.")
    lines.append("- Add focused tests before promotion.")
    lines.append("- Re-run `audit` after the next forge or manual refinement pass.")
    lines.append("")
    lines.append("## Manual Review Prompts")
    lines.append("")
    lines.append("- Does the runtime code actually execute each plan step, rather than only storing it in metadata?")
    lines.append("- Are paper-specific assumptions exposed as parameters instead of hidden logic?")
    lines.append("- Is the draft still relying on the generic forge baseline?")
    lines.append("")
    return "\n".join(lines)
