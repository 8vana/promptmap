from __future__ import annotations

import asyncio
import ast
import hashlib
import importlib.util
from dataclasses import dataclass
import json
from pathlib import Path
import py_compile
from typing import Any

import yaml

from promptmap.engine.base_attack import BaseAttack
from promptmap.engine.base_scorer import BaseScorer
from promptmap.engine.base_target import TargetAdapter
from promptmap.engine.context import AttackContext
from promptmap.engine.events import EVT_COMPLETE, EVT_PROMPT, EVT_RESPONSE
from promptmap.engine.models import AttackResult, ScorerResult
from promptmap.memory.session_memory import SessionMemory
from promptmap.registry.attack_spec import AttackSpec

from .common import normalize_attack_id, to_class_name
from .lifecycle import FORGE_STATUS_DRAFT
from .quality import extract_forge_status, find_placeholder_markers
from .single_turn import (
    SUPPORTED_SINGLE_TURN_SKELETONS,
    has_complete_step_symbol_map,
    is_single_turn_family,
    is_supported_single_turn_skeleton,
)


@dataclass(frozen=True)
class VerifyConfig:
    attack_id: str
    staging_dir: Path


@dataclass(frozen=True)
class VerifyOutcome:
    verification_report_text: str
    verification_report: dict[str, Any]


def run_verify(config: VerifyConfig) -> VerifyOutcome:
    plan_path = config.staging_dir / "implementation_plan.json"
    module_path = config.staging_dir / "attack_module.py"
    catalog_path = config.staging_dir / "attack_catalog.yaml"
    manifest_path = config.staging_dir / "manifest.json"
    reference_manifest_path = config.staging_dir / "reference_manifest.json"
    reference_snippets_dir = config.staging_dir / "reference_snippets"

    missing = [
        str(path.name)
        for path in (plan_path, module_path, catalog_path)
        if not path.exists()
    ]
    if missing:
        raise ValueError(
            f"Missing required staging artifacts for verify: {', '.join(missing)}"
        )

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    module_source = module_path.read_text(encoding="utf-8")
    catalog_data = yaml.safe_load(catalog_path.read_text(encoding="utf-8")) or {}
    manifest = _read_json_dict(manifest_path)
    reference_manifest = _read_json_dict(reference_manifest_path)
    module_metadata = _extract_module_metadata(module_source)
    module_forge_status = extract_forge_status(module_source)
    placeholder_markers = find_placeholder_markers(module_source)
    artifact_fingerprints = {
        "implementation_plan.json": _sha256_text(plan_path.read_text(encoding="utf-8")),
        "attack_module.py": _sha256_text(module_source),
        "attack_catalog.yaml": _sha256_text(catalog_path.read_text(encoding="utf-8")),
    }

    attack_id = normalize_attack_id(str(plan.get("attack_id") or config.attack_id))
    expected_class_name = to_class_name(attack_id)
    expected_module_name = f"{attack_id}_attack"
    expected_import_path = f"promptmap.attacks.{expected_module_name}:{expected_class_name}"

    categories: list[str] = []
    recommended_next_actions: list[str] = []

    plan_checks = _verify_plan_contract(plan)
    if not plan_checks["ok"]:
        categories.append("plan_contract_invalid")
        recommended_next_actions.append(
            "Fix implementation_plan.json contract issues before promotion."
        )

    py_compile_ok, py_compile_error = _check_py_compile(module_path)
    if not py_compile_ok:
        categories.append("py_compile_failed")
        recommended_next_actions.append("Fix Python syntax errors in attack_module.py.")

    import_smoke = _verify_module_import(
        module_path=module_path,
        attack_id=attack_id,
        expected_class_name=expected_class_name,
    )
    if not import_smoke["ok"]:
        categories.append("module_import_smoke_failed")
        recommended_next_actions.append(
            "Ensure the generated module imports cleanly and exposes a BaseAttack subclass."
        )

    runtime_checks = _verify_runtime_contract(
        module_path=module_path,
        attack_id=attack_id,
        expected_class_name=expected_class_name,
        family=str(plan.get("family") or ""),
    )
    for category in runtime_checks["failure_categories"]:
        if category not in categories:
            categories.append(category)
    if runtime_checks["failure_categories"]:
        recommended_next_actions.append(
            "Fix runtime smoke failures so the attack executes and emits the expected event contract."
        )

    catalog_checks = _verify_catalog(
        catalog_data=catalog_data,
        expected_import_path=expected_import_path,
        expected_attack_id=attack_id,
    )
    if not catalog_checks["schema_ok"]:
        categories.append("catalog_schema_invalid")
        recommended_next_actions.append("Fix attack_catalog.yaml schema issues.")
    if not catalog_checks["import_path_matches_expected"]:
        categories.append("catalog_import_path_mismatch")
        recommended_next_actions.append(
            "Align attack_catalog.yaml import_path with the promotion target."
        )

    single_turn_checks = _verify_single_turn_profile(
        plan=plan,
        manifest=manifest,
        module_metadata=module_metadata,
        catalog_data=catalog_data,
    )
    if not single_turn_checks["ok"]:
        categories.append("single_turn_profile_incomplete")
        recommended_next_actions.append(
            "Complete the single-turn profile checks before treating this draft as single-turn complete."
        )

    if module_forge_status == FORGE_STATUS_DRAFT:
        categories.append("draft_artifact_detected")
        recommended_next_actions.append(
            "Replace draft forge markers with a reviewed implementation before promotion."
        )
    if placeholder_markers:
        categories.append("placeholder_logic_detected")
        recommended_next_actions.append(
            "Remove TODO and placeholder logic markers before treating this attack as production-ready."
        )
    manifest_forge_status = str(manifest.get("forge_phase_b", {}).get("forge_status") or "").strip()
    if manifest_forge_status and module_forge_status and manifest_forge_status != module_forge_status:
        categories.append("forge_status_mismatch")
        recommended_next_actions.append(
            "Align manifest forge_status with the module metadata before promotion."
        )

    reference_checks = _verify_reference_artifacts(
        reference_manifest=reference_manifest,
        reference_snippets_dir=reference_snippets_dir,
    )
    if not reference_checks["ok"]:
        categories.append("reference_artifact_mismatch")
        recommended_next_actions.append(
            "Repair reference_manifest.json / reference_snippets consistency."
        )

    categories = list(dict.fromkeys(categories))
    recommended_next_actions = list(dict.fromkeys(recommended_next_actions))

    if any(
        category in categories
        for category in (
                "plan_contract_invalid",
                "py_compile_failed",
                "module_import_smoke_failed",
                "catalog_schema_invalid",
                "runtime_smoke_failed",
                "event_contract_failed",
                "result_contract_failed",
            )
    ):
        verdict = "blocked_by_verification_failure"
    elif categories:
        verdict = "pass_with_warnings"
    else:
        verdict = "pass"

    report = {
        "attack_id": attack_id,
        "verdict": verdict,
        "categories": categories,
        "artifact_fingerprints": artifact_fingerprints,
        "plan_checks": plan_checks,
        "module_checks": {
            "py_compile_ok": py_compile_ok,
            "py_compile_error": py_compile_error,
            **import_smoke,
            "forge_status": module_forge_status,
            "placeholder_markers": placeholder_markers,
        },
        "runtime_checks": runtime_checks,
        "catalog_checks": catalog_checks,
        "single_turn_checks": single_turn_checks,
        "reference_checks": reference_checks,
        "recommended_next_actions": recommended_next_actions,
        "promotion_targets": manifest.get("promotion_targets", {}),
    }
    return VerifyOutcome(
        verification_report_text=_render_verification_report(report),
        verification_report=report,
    )


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _verify_plan_contract(plan: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    required = [
        "attack_id",
        "display_name",
        "paper_title",
        "paper_url",
        "family",
        "algorithm_steps",
        "paper_evidence",
        "repo_evidence",
        "operator_notes",
    ]
    for key in required:
        if key not in plan:
            errors.append(f"Missing required plan key: {key}")

    step_ids: list[str] = []
    if isinstance(plan.get("algorithm_steps"), list):
        for step in plan.get("algorithm_steps", []):
            if not isinstance(step, dict):
                errors.append("algorithm_steps contains a non-object entry")
                continue
            step_id = str(step.get("step_id") or "").strip()
            if not step_id:
                errors.append("algorithm_steps contains an entry with empty step_id")
                continue
            step_ids.append(step_id)

    if len(step_ids) != len(set(step_ids)):
        errors.append("algorithm_steps contains duplicate step_id values")

    known_evidence_ids = set()
    for section_name in ("paper_evidence", "repo_evidence", "operator_notes"):
        section = plan.get(section_name)
        if not isinstance(section, list):
            errors.append(f"{section_name} must be a list")
            continue
        for record in section:
            if not isinstance(record, dict):
                errors.append(f"{section_name} contains a non-object entry")
                continue
            evidence_id = str(record.get("evidence_id") or "").strip()
            if not evidence_id:
                errors.append(f"{section_name} contains an entry with empty evidence_id")
                continue
            known_evidence_ids.add(evidence_id)

    for step in plan.get("algorithm_steps", []) if isinstance(plan.get("algorithm_steps"), list) else []:
        if not isinstance(step, dict):
            continue
        for ref in step.get("evidence_refs", []) or []:
            if ref not in known_evidence_ids:
                errors.append(f"Unknown evidence_ref in step {step.get('step_id')}: {ref}")

    return {
        "ok": not errors,
        "errors": errors,
        "step_count": len(step_ids),
        "known_evidence_count": len(known_evidence_ids),
    }


def _check_py_compile(module_path: Path) -> tuple[bool, str]:
    try:
        py_compile.compile(str(module_path), doraise=True)
        return True, ""
    except py_compile.PyCompileError as exc:
        return False, str(exc)


def _load_attack_class(
    *,
    module_path: Path,
    attack_id: str,
    expected_class_name: str,
) -> tuple[type[BaseAttack] | None, str]:
    module_name = f"_promptmap_scaffold_verify_{attack_id}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            return None, "Could not create import spec from staging module."
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, expected_class_name, None)
        if not isinstance(cls, type):
            return None, f"Expected class '{expected_class_name}' not found."
        if not issubclass(cls, BaseAttack):
            return None, f"{expected_class_name} is not a BaseAttack subclass."
        return cls, ""
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _verify_module_import(
    *,
    module_path: Path,
    attack_id: str,
    expected_class_name: str,
) -> dict[str, Any]:
    cls, error = _load_attack_class(
        module_path=module_path,
        attack_id=attack_id,
        expected_class_name=expected_class_name,
    )
    return {
        "ok": cls is not None,
        "import_error": error,
        "class_name": expected_class_name,
        "is_base_attack_subclass": cls is not None,
    }


def _verify_runtime_contract(
    *,
    module_path: Path,
    attack_id: str,
    expected_class_name: str,
    family: str,
) -> dict[str, Any]:
    cls, error = _load_attack_class(
        module_path=module_path,
        attack_id=attack_id,
        expected_class_name=expected_class_name,
    )
    if cls is None:
        return {
            "ok": False,
            "failure_categories": ["runtime_smoke_failed"],
            "errors": [error],
            "event_types": [],
            "result_turns": None,
            "result_metadata_keys": [],
        }

    try:
        result, event_types = asyncio.run(_exercise_attack(cls))
    except Exception as exc:
        return {
            "ok": False,
            "failure_categories": ["runtime_smoke_failed"],
            "errors": [f"{type(exc).__name__}: {exc}"],
            "event_types": [],
            "result_turns": None,
            "result_metadata_keys": [],
        }

    failure_categories: list[str] = []
    errors: list[str] = []
    missing_events = [
        event_type
        for event_type in (EVT_PROMPT, EVT_RESPONSE, EVT_COMPLETE)
        if event_type not in event_types
    ]
    if missing_events:
        failure_categories.append("event_contract_failed")
        errors.append("Missing emitted event types: " + ", ".join(missing_events))
    if not isinstance(result, AttackResult):
        failure_categories.append("result_contract_failed")
        errors.append("run() did not return an AttackResult instance.")
    else:
        if result.turns < 1:
            failure_categories.append("result_contract_failed")
            errors.append("AttackResult.turns must be >= 1.")
        if not isinstance(result.metadata, dict):
            failure_categories.append("result_contract_failed")
            errors.append("AttackResult.metadata must be a dict.")
        if family == "single_turn" and result.turns != 1:
            failure_categories.append("result_contract_failed")
            errors.append(f"Single-turn attacks must finish in exactly 1 turn, got {result.turns}.")

    return {
        "ok": not failure_categories,
        "failure_categories": failure_categories,
        "errors": errors,
        "event_types": event_types,
        "result_turns": result.turns if isinstance(result, AttackResult) else None,
        "result_metadata_keys": sorted(result.metadata.keys()) if isinstance(result, AttackResult) else [],
    }


async def _exercise_attack(cls: type[BaseAttack]) -> tuple[AttackResult, list[str]]:
    progress_queue: asyncio.Queue = asyncio.Queue()
    target = _RuntimeSmokeTarget()
    ctx = AttackContext(
        target=target,
        adversarial_target=target,
        scorer=_RuntimeSmokeScorer(),
        converters=[_RuntimeSmokeConverter()],
        memory=SessionMemory(),
        progress_queue=progress_queue,
    )
    result = await cls().run(
        ctx,
        "Explain an innocuous process in detail.",
        candidate_instructions=["Provide a harmless example with concrete steps."],
        candidate_instruction="Provide a harmless example with concrete steps.",
        seed_prompt="Describe a harmless household task.",
        selected_instruction_count=1,
    )
    event_types: list[str] = []
    while not progress_queue.empty():
        event = progress_queue.get_nowait()
        event_types.append(str(getattr(event, "type", "")))
    return result, event_types


class _RuntimeSmokeTarget(TargetAdapter):
    async def send(self, prompt: str, conversation_id: str) -> str:
        return f"stub target response: {prompt[:60]}"


class _RuntimeSmokeScorer(BaseScorer):
    async def score(self, response: str, objective: str) -> ScorerResult:
        return ScorerResult(score=0.25, achieved=False, rationale="runtime smoke")


class _RuntimeSmokeConverter:
    async def convert(self, text: str) -> str:
        return text


def _verify_catalog(
    *,
    catalog_data: dict[str, Any],
    expected_import_path: str,
    expected_attack_id: str,
) -> dict[str, Any]:
    schema_ok = True
    schema_error = ""
    try:
        spec = AttackSpec(**catalog_data)
    except Exception as exc:
        schema_ok = False
        schema_error = f"{type(exc).__name__}: {exc}"
        spec = None

    import_path = str(catalog_data.get("import_path") or "")
    return {
        "schema_ok": schema_ok,
        "schema_error": schema_error,
        "attack_id_matches_expected": str(catalog_data.get("attack_id") or "") == expected_attack_id,
        "import_path_matches_expected": import_path == expected_import_path,
        "import_path": import_path,
        "expected_import_path": expected_import_path,
        "registered_name": str(catalog_data.get("registered_name") or ""),
        "supports_benchmark": bool(catalog_data.get("supports_benchmark")),
        "spec_loaded": spec is not None,
    }


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
                "EXECUTION_SKELETON",
                "STEP_SYMBOL_MAP",
                "PLAN_STEP_IDS",
            }:
                try:
                    metadata[target.id] = ast.literal_eval(node.value)
                except Exception:
                    continue
    return metadata


def _verify_single_turn_profile(
    *,
    plan: dict[str, Any],
    manifest: dict[str, Any],
    module_metadata: dict[str, Any],
    catalog_data: dict[str, Any],
) -> dict[str, Any]:
    family = str(plan.get("family") or "").strip()
    if not is_single_turn_family(family):
        return {
            "applicable": False,
            "ok": True,
            "workflow_profile": str(manifest.get("forge_phase_b", {}).get("workflow_profile") or ""),
            "supported_skeletons": list(SUPPORTED_SINGLE_TURN_SKELETONS),
            "errors": [],
        }

    execution_skeleton = str(
        manifest.get("forge_phase_b", {}).get("execution_skeleton")
        or module_metadata.get("EXECUTION_SKELETON")
        or ""
    )
    workflow_profile = str(manifest.get("forge_phase_b", {}).get("workflow_profile") or "")
    if not workflow_profile and is_supported_single_turn_skeleton(execution_skeleton):
        workflow_profile = "single_turn"
    step_symbol_map = module_metadata.get("STEP_SYMBOL_MAP", {})
    registered_name = str(catalog_data.get("registered_name") or "")
    errors: list[str] = []

    if not is_supported_single_turn_skeleton(execution_skeleton):
        errors.append(
            f"Unsupported single-turn execution skeleton: {execution_skeleton or 'missing'}"
        )
    if workflow_profile != "single_turn":
        errors.append(
            f"workflow_profile should be 'single_turn' for single-turn plans, got: {workflow_profile or 'missing'}"
        )
    if not registered_name.startswith("Single_"):
        errors.append(
            f"registered_name should use the Single_ prefix for single-turn attacks: {registered_name or 'missing'}"
        )
    if not has_complete_step_symbol_map(
        plan.get("algorithm_steps", []) if isinstance(plan.get("algorithm_steps"), list) else [],
        step_symbol_map if isinstance(step_symbol_map, dict) else {},
    ):
        errors.append("STEP_SYMBOL_MAP does not cover every algorithm step.")

    return {
        "applicable": True,
        "ok": not errors,
        "workflow_profile": workflow_profile,
        "execution_skeleton": execution_skeleton,
        "supported_skeletons": list(SUPPORTED_SINGLE_TURN_SKELETONS),
        "errors": errors,
    }


def _verify_reference_artifacts(
    *,
    reference_manifest: dict[str, Any],
    reference_snippets_dir: Path,
) -> dict[str, Any]:
    errors: list[str] = []
    if not reference_manifest and not reference_snippets_dir.exists():
        return {
            "ok": True,
            "reference_present": False,
            "snippet_file_count": 0,
            "manifest_snippet_count": 0,
            "errors": [],
        }

    manifest_snippets = reference_manifest.get("snippets") if isinstance(reference_manifest, dict) else None
    if not isinstance(manifest_snippets, list):
        errors.append("reference_manifest.json is missing a valid 'snippets' list")
        manifest_snippets = []

    snippet_files = sorted(reference_snippets_dir.glob("*")) if reference_snippets_dir.exists() else []
    manifest_filenames = []
    for snippet in manifest_snippets:
        if not isinstance(snippet, dict):
            errors.append("reference_manifest.json contains a non-object snippet entry")
            continue
        filename = str(snippet.get("snippet_filename") or "").strip()
        if not filename:
            errors.append("reference_manifest.json snippet entry has empty snippet_filename")
            continue
        manifest_filenames.append(filename)
        file_path = reference_snippets_dir / filename
        if not file_path.exists():
            errors.append(f"Missing reference snippet file: {filename}")
            continue
        expected_sha = str(snippet.get("sha256") or "").strip()
        if expected_sha:
            actual_sha = hashlib.sha256(file_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
            if actual_sha != expected_sha:
                errors.append(f"SHA mismatch for reference snippet: {filename}")

    file_names = [path.name for path in snippet_files if path.is_file()]
    extra_files = sorted(set(file_names) - set(manifest_filenames))
    if extra_files:
        errors.append(
            "reference_snippets contains files not listed in reference_manifest.json: "
            + ", ".join(extra_files)
        )

    manifest_count = int(reference_manifest.get("snippet_count") or 0) if reference_manifest else 0
    if reference_manifest and manifest_count != len(manifest_filenames):
        errors.append(
            f"reference_manifest.json snippet_count={manifest_count} does not match listed snippets={len(manifest_filenames)}"
        )

    return {
        "ok": not errors,
        "reference_present": True,
        "snippet_file_count": len(file_names),
        "manifest_snippet_count": len(manifest_filenames),
        "errors": errors,
    }


def _render_verification_report(report: dict[str, Any]) -> str:
    lines: list[str] = []
    lines.append(f"# Verification Report: {report['attack_id']}")
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    lines.append(f"- `verdict`: `{report['verdict']}`")
    lines.append(
        f"- `categories`: {', '.join(report['categories']) if report['categories'] else 'none'}"
    )
    lines.append("")
    lines.append("## Plan Checks")
    lines.append("")
    lines.append(f"- `ok`: `{str(report['plan_checks']['ok']).lower()}`")
    lines.append(f"- `step_count`: `{report['plan_checks']['step_count']}`")
    lines.append(f"- `known_evidence_count`: `{report['plan_checks']['known_evidence_count']}`")
    if report["plan_checks"]["errors"]:
        lines.append(f"- `errors`: {'; '.join(report['plan_checks']['errors'])}")
    lines.append("")
    lines.append("## Module Checks")
    lines.append("")
    lines.append(f"- `py_compile_ok`: `{str(report['module_checks']['py_compile_ok']).lower()}`")
    lines.append(f"- `import_smoke_ok`: `{str(report['module_checks']['ok']).lower()}`")
    lines.append(f"- `class_name`: `{report['module_checks']['class_name']}`")
    lines.append(
        f"- `is_base_attack_subclass`: `{str(report['module_checks']['is_base_attack_subclass']).lower()}`"
    )
    lines.append(f"- `forge_status`: `{report['module_checks']['forge_status'] or 'missing'}`")
    lines.append(
        f"- `placeholder_markers`: {', '.join(report['module_checks']['placeholder_markers']) if report['module_checks']['placeholder_markers'] else 'none'}"
    )
    if report["module_checks"]["py_compile_error"]:
        lines.append(f"- `py_compile_error`: {report['module_checks']['py_compile_error']}")
    if report["module_checks"]["import_error"]:
        lines.append(f"- `import_error`: {report['module_checks']['import_error']}")
    lines.append("")
    lines.append("## Runtime Checks")
    lines.append("")
    lines.append(f"- `ok`: `{str(report['runtime_checks']['ok']).lower()}`")
    lines.append(
        f"- `failure_categories`: {', '.join(report['runtime_checks']['failure_categories']) if report['runtime_checks']['failure_categories'] else 'none'}"
    )
    lines.append(
        f"- `event_types`: {', '.join(report['runtime_checks']['event_types']) if report['runtime_checks']['event_types'] else 'none'}"
    )
    lines.append(f"- `result_turns`: `{report['runtime_checks']['result_turns']}`")
    if report["runtime_checks"]["errors"]:
        lines.append(f"- `errors`: {'; '.join(report['runtime_checks']['errors'])}")
    lines.append("")
    lines.append("## Catalog Checks")
    lines.append("")
    lines.append(f"- `schema_ok`: `{str(report['catalog_checks']['schema_ok']).lower()}`")
    lines.append(
        f"- `attack_id_matches_expected`: `{str(report['catalog_checks']['attack_id_matches_expected']).lower()}`"
    )
    lines.append(
        f"- `import_path_matches_expected`: `{str(report['catalog_checks']['import_path_matches_expected']).lower()}`"
    )
    lines.append(f"- `import_path`: `{report['catalog_checks']['import_path']}`")
    lines.append(
        f"- `expected_import_path`: `{report['catalog_checks']['expected_import_path']}`"
    )
    if report["catalog_checks"]["schema_error"]:
        lines.append(f"- `schema_error`: {report['catalog_checks']['schema_error']}")
    lines.append("")
    lines.append("## Reference Checks")
    lines.append("")
    lines.append(
        f"- `reference_present`: `{str(report['reference_checks']['reference_present']).lower()}`"
    )
    lines.append(
        f"- `ok`: `{str(report['reference_checks']['ok']).lower()}`"
    )
    lines.append(
        f"- `snippet_file_count`: `{report['reference_checks']['snippet_file_count']}`"
    )
    lines.append(
        f"- `manifest_snippet_count`: `{report['reference_checks']['manifest_snippet_count']}`"
    )
    if report["reference_checks"]["errors"]:
        lines.append(f"- `errors`: {'; '.join(report['reference_checks']['errors'])}")
    lines.append("")
    lines.append("## Single-Turn Checks")
    lines.append("")
    lines.append(
        f"- `applicable`: `{str(report['single_turn_checks']['applicable']).lower()}`"
    )
    lines.append(
        f"- `ok`: `{str(report['single_turn_checks']['ok']).lower()}`"
    )
    workflow_profile = report["single_turn_checks"].get("workflow_profile", "")
    if workflow_profile:
        lines.append(f"- `workflow_profile`: `{workflow_profile}`")
    execution_skeleton = report["single_turn_checks"].get("execution_skeleton", "")
    if execution_skeleton:
        lines.append(f"- `execution_skeleton`: `{execution_skeleton}`")
    if report["single_turn_checks"]["errors"]:
        lines.append(f"- `errors`: {'; '.join(report['single_turn_checks']['errors'])}")
    lines.append("")
    lines.append("## Recommended Actions")
    lines.append("")
    for action in report["recommended_next_actions"] or ["No additional actions recorded."]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)
