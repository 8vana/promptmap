from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import py_compile
from typing import Any

import yaml

from .quality import extract_forge_status, find_placeholder_markers


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
    generation_notes_path = config.staging_dir / "generation_notes.md"

    if not plan_path.exists():
        raise ValueError(f"Missing implementation plan: {plan_path}")
    if not module_path.exists():
        raise ValueError(f"Missing generated attack module: {module_path}")
    if not catalog_path.exists():
        raise ValueError(f"Missing generated attack catalog: {catalog_path}")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    module_source = module_path.read_text(encoding="utf-8")
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    generation_notes_text = _read_optional_text(generation_notes_path)
    artifact_fingerprints = {
        "implementation_plan.json": _sha256_text(plan_path.read_text(encoding="utf-8")),
        "attack_module.py": _sha256_text(module_source),
        "attack_catalog.yaml": _sha256_text(catalog_path.read_text(encoding="utf-8")),
        "generation_notes.md": _sha256_text(generation_notes_text) if generation_notes_text else "",
    }

    module_runtime_source = _runtime_source(module_source)
    py_compile_ok, py_compile_error = _check_py_compile(module_path)
    module_metadata = _extract_module_metadata(module_source)
    method_sources = _extract_method_sources(module_source)
    run_source = method_sources.get("run", "")
    module_forge_status = extract_forge_status(module_source)
    placeholder_markers = find_placeholder_markers(module_source)

    generic_baseline_detected = "forge draft executing plan-driven baseline flow" in module_source

    step_results = [
        _audit_step(
            step,
            runtime_source=module_runtime_source,
            generic_baseline_detected=generic_baseline_detected,
            step_symbol_map=module_metadata.get("STEP_SYMBOL_MAP", {}),
            step_contracts=module_metadata.get("STEP_IMPLEMENTATION_CONTRACT", {}),
            method_sources=method_sources,
            run_source=run_source,
        )
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
    if partial_steps:
        categories.append("partial_algorithm_steps")
        recommended_actions.append(
            "Finish the partially implemented plan steps before promotion."
        )
    if generic_baseline_detected:
        categories.append("unsafe_inference_detected")
        recommended_actions.append(
            "Replace the generic forge baseline with paper-specific prompt construction and control flow."
        )
    if module_forge_status == "draft":
        categories.append("draft_artifact_detected")
        recommended_actions.append(
            "Promote only after the module no longer declares forge_status=draft."
        )
    if placeholder_markers:
        categories.append("placeholder_logic_detected")
        recommended_actions.append(
            "Remove TODO and placeholder markers before promotion."
        )

    catalog_checks = _audit_catalog(plan, catalog)
    repo_support_checks = _audit_repo_support(
        plan=plan,
        module_metadata=module_metadata,
        generation_notes_text=generation_notes_text,
    )
    if not _catalog_supports_benchmark(catalog):
        categories.append("benchmark_not_advised")
        recommended_actions.append(
            "Keep supports_benchmark disabled until the implementation is paper-faithful and tested."
        )
    if repo_support_checks["silent_repo_dependency_detected"]:
        categories.append("silent_repo_dependency_detected")
        recommended_actions.append(
            "Surface repo-derived behavior explicitly in generation notes and module metadata before promotion."
        )
    if catalog_checks["mismatches"]:
        recommended_actions.append(
            "Resolve catalog mismatches so runtime metadata stays aligned with the implementation plan."
        )

    categories = list(dict.fromkeys(categories))
    recommended_actions = list(dict.fromkeys(recommended_actions))

    if not py_compile_ok:
        verdict = "blocked_by_missing_information"
        recommended_actions.append("Fix Python syntax/import issues before continuing.")
    elif missing_steps or partial_steps or generic_baseline_detected or placeholder_markers or module_forge_status == "draft":
        verdict = "needs_refinement"
    else:
        verdict = "pass_with_review"

    audit_verdict = {
        "attack_id": plan.get("attack_id") or config.attack_id,
        "verdict": verdict,
        "categories": categories,
        "artifact_fingerprints": artifact_fingerprints,
        "module_checks": {
            "py_compile_ok": py_compile_ok,
            "py_compile_error": py_compile_error,
            "generic_baseline_detected": generic_baseline_detected,
            "execution_skeleton": module_metadata.get("EXECUTION_SKELETON", ""),
            "generation_notes_present": bool(generation_notes_text.strip()),
            "forge_status": module_forge_status,
            "placeholder_markers": placeholder_markers,
            "step_contracts_present": bool(module_metadata.get("STEP_IMPLEMENTATION_CONTRACT")),
        },
        "catalog_checks": catalog_checks,
        "repo_support_checks": repo_support_checks,
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


def _read_optional_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def _extract_module_metadata(module_source: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    try:
        tree = ast.parse(module_source)
    except SyntaxError:
        return metadata
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id in {
                "STEP_SYMBOL_MAP",
                "EXECUTION_SKELETON",
                "PLAN_STEP_IDS",
                "REPO_DERIVED_HINTS",
                "DEFAULT_PARAMS",
                "STEP_IMPLEMENTATION_CONTRACT",
            }:
                try:
                    metadata[target.id] = ast.literal_eval(node.value)
                except Exception:
                    continue
    return metadata


def _extract_method_sources(module_source: str) -> dict[str, str]:
    methods: dict[str, str] = {}
    try:
        tree = ast.parse(module_source)
    except SyntaxError:
        return methods
    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                methods[child.name] = ast.get_source_segment(module_source, child) or ""
    return methods


def _audit_step(
    step: dict[str, Any],
    *,
    runtime_source: str,
    generic_baseline_detected: bool,
    step_symbol_map: dict[str, Any],
    step_contracts: dict[str, Any],
    method_sources: dict[str, str],
    run_source: str,
) -> dict[str, str]:
    step_id = str(step.get("step_id") or "").strip()
    title = str(step.get("title") or "").strip()
    lowered = step_id.lower()
    source_lower = runtime_source.lower()

    status = "missing"
    reason = "No implementation signal detected for this plan step."

    mapping = step_symbol_map.get(step_id) if isinstance(step_symbol_map, dict) else None
    contract = step_contracts.get(step_id) if isinstance(step_contracts, dict) else None
    mapped_symbol = ""
    todo_only = False
    if isinstance(mapping, dict):
        mapped_symbol = str(mapping.get("target_symbol") or "")
        todo_only = bool(mapping.get("todo_only"))
    if not mapped_symbol and isinstance(contract, dict):
        mapped_symbol = str(contract.get("target_symbol") or "")
        todo_only = bool(contract.get("todo_only"))

    if mapped_symbol.startswith("_"):
        method_name = mapped_symbol
        method_source = method_sources.get(method_name, "")
        method_lower = method_source.lower()
        method_called = bool(run_source and method_name in run_source)
        if method_source:
            has_todo = "todo(" in method_lower or "todo:" in method_lower
            has_placeholders = bool(find_placeholder_markers(method_source))
            has_substantive_logic = any(
                token in method_lower
                for token in (
                    "return ",
                    "await ",
                    "for ",
                    "if ",
                    "sorted(",
                    "append(",
                    "score(",
                    "send(",
                    "emit(",
                )
            )
            if method_called and has_substantive_logic and not has_todo and not has_placeholders and not todo_only:
                status = "implemented"
                reason = f"Mapped helper `{mapped_symbol}` exists, is called from `run`, and contains non-TODO logic."
            elif method_called or has_substantive_logic:
                status = "partial"
                reason = f"Mapped helper `{mapped_symbol}` exists, but still contains TODO-driven or placeholder behavior."
            return {
                "step_id": step_id,
                "title": title,
                "status": status,
                "reason": reason,
            }

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


def _audit_repo_support(
    *,
    plan: dict[str, Any],
    module_metadata: dict[str, Any],
    generation_notes_text: str,
) -> dict[str, Any]:
    repo_evidence = plan.get("repo_evidence") or []
    divergences = plan.get("divergences") or []
    repo_hints = module_metadata.get("REPO_DERIVED_HINTS", {})
    default_params = module_metadata.get("DEFAULT_PARAMS", {})

    repo_hint_keys = sorted(repo_hints.keys()) if isinstance(repo_hints, dict) else []
    default_param_keys = sorted(default_params.keys()) if isinstance(default_params, dict) else []
    divergence_topics = [
        str(item.get("topic") or "").strip()
        for item in divergences
        if isinstance(item, dict) and str(item.get("topic") or "").strip()
    ]

    notes_lower = generation_notes_text.lower()
    generation_notes_repo_section_present = (
        "## repo support".lower() in notes_lower
        or "## repo-derived hints".lower() in notes_lower
    )

    missing_signals: list[str] = []
    if repo_hint_keys:
        missing_default_keys = [key for key in repo_hint_keys if key not in default_param_keys]
        if missing_default_keys:
            missing_signals.append(
                "Repo-derived hints were not mirrored into DEFAULT_PARAMS: "
                + ", ".join(missing_default_keys)
            )
        if not generation_notes_repo_section_present:
            missing_signals.append("Generation notes do not include a repo support section.")
        missing_topics = [key for key in repo_hint_keys if key.lower() not in notes_lower]
        if missing_topics:
            missing_signals.append(
                "Generation notes do not mention repo-derived hint topics: "
                + ", ".join(missing_topics)
            )

    if divergences:
        if "## divergences" not in notes_lower:
            missing_signals.append("Generation notes do not include a divergences section.")
        missing_divergence_topics = [
            topic for topic in divergence_topics if topic.lower() not in notes_lower
        ]
        if missing_divergence_topics:
            missing_signals.append(
                "Generation notes do not mention divergence topics: "
                + ", ".join(missing_divergence_topics)
            )

    return {
        "repo_evidence_count": len(repo_evidence),
        "divergence_count": len(divergences),
        "repo_derived_hint_keys": repo_hint_keys,
        "default_param_keys": default_param_keys,
        "generation_notes_repo_section_present": generation_notes_repo_section_present,
        "silent_repo_dependency_detected": bool(missing_signals),
        "missing_signals": missing_signals,
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
    lines.append(
        f"- `execution_skeleton`: `{verdict['module_checks']['execution_skeleton'] or 'unknown'}`"
    )
    lines.append(
        f"- `generation_notes_present`: `{str(verdict['module_checks']['generation_notes_present']).lower()}`"
    )
    lines.append(f"- `forge_status`: `{verdict['module_checks']['forge_status'] or 'missing'}`")
    lines.append(
        f"- `placeholder_markers`: {', '.join(verdict['module_checks']['placeholder_markers']) if verdict['module_checks']['placeholder_markers'] else 'none'}"
    )
    lines.append(
        f"- `step_contracts_present`: `{str(verdict['module_checks']['step_contracts_present']).lower()}`"
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
    lines.append("## Repo Support Checks")
    lines.append("")
    lines.append(
        f"- `repo_evidence_count`: `{verdict['repo_support_checks']['repo_evidence_count']}`"
    )
    lines.append(
        f"- `divergence_count`: `{verdict['repo_support_checks']['divergence_count']}`"
    )
    lines.append(
        f"- `repo_derived_hint_keys`: {', '.join(verdict['repo_support_checks']['repo_derived_hint_keys']) if verdict['repo_support_checks']['repo_derived_hint_keys'] else 'none'}"
    )
    lines.append(
        f"- `generation_notes_repo_section_present`: `{str(verdict['repo_support_checks']['generation_notes_repo_section_present']).lower()}`"
    )
    lines.append(
        f"- `silent_repo_dependency_detected`: `{str(verdict['repo_support_checks']['silent_repo_dependency_detected']).lower()}`"
    )
    if verdict["repo_support_checks"]["missing_signals"]:
        lines.append(
            f"- `missing_signals`: {'; '.join(verdict['repo_support_checks']['missing_signals'])}"
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
    for missing_signal in verdict.get("repo_support_checks", {}).get("missing_signals", []):
        lines.append(f"- Repo support gap: {missing_signal}")
    for marker in verdict.get("module_checks", {}).get("placeholder_markers", []):
        lines.append(f"- Remove placeholder marker: `{marker}`")
    if not catalog_checks["supports_benchmark"]:
        lines.append("- Keep `supports_benchmark: false` until the audit findings are resolved.")
    lines.append("- Add focused tests before promotion.")
    lines.append("- Re-run `audit` after the next forge or manual refinement pass.")
    lines.append("")
    lines.append("## Manual Review Prompts")
    lines.append("")
    lines.append("- Does the runtime code actually execute each plan step, rather than only storing it in metadata?")
    lines.append("- Are paper-specific assumptions exposed as parameters instead of hidden logic?")
    lines.append("- Does the selected execution skeleton match the paper's real control flow?")
    lines.append("")
    return "\n".join(lines)
