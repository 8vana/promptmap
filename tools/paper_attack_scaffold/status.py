from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from .lifecycle import (
    WORKFLOW_STAGE_BENCHMARK_CANDIDATE,
    WORKFLOW_STAGE_FORGED,
    WORKFLOW_STAGE_NEEDS_REFINEMENT,
    WORKFLOW_STAGE_NOT_STARTED,
    WORKFLOW_STAGE_PLANNED,
    WORKFLOW_STAGE_PROMOTED,
    WORKFLOW_STAGE_PROMOTION_READY,
    WORKFLOW_STAGE_REVIEW_READY,
    WORKFLOW_STAGE_SCAFFOLDED,
    WORKFLOW_STAGE_VERIFICATION_BLOCKED,
    WORKFLOW_STATUS_SCHEMA_VERSION,
    build_consistency_checks,
    derive_forge_status,
)
from .single_turn import (
    SUPPORTED_SINGLE_TURN_SKELETONS,
    is_single_turn_family,
    is_supported_single_turn_skeleton,
)


@dataclass(frozen=True)
class WorkflowStatusConfig:
    attack_id: str
    staging_dir: Path


@dataclass(frozen=True)
class WorkflowStatusOutcome:
    workflow_status_text: str
    workflow_status: dict[str, Any]


def run_workflow_status(config: WorkflowStatusConfig) -> WorkflowStatusOutcome:
    manifest_path = config.staging_dir / "manifest.json"
    plan_path = config.staging_dir / "implementation_plan.json"
    module_path = config.staging_dir / "attack_module.py"
    catalog_path = config.staging_dir / "attack_catalog.yaml"
    audit_path = config.staging_dir / "audit_verdict.json"
    verify_path = config.staging_dir / "verification_report.json"

    manifest = _read_json_dict(manifest_path)
    plan = _read_json_dict(plan_path)
    audit = _read_json_dict(audit_path)
    verify = _read_json_dict(verify_path)
    catalog = _read_yaml_dict(catalog_path)

    plan_present = plan_path.exists() and bool(plan)
    forge_present = module_path.exists() and catalog_path.exists() and bool(
        manifest.get("forge_phase_b")
    )
    audit_present = audit_path.exists() and bool(audit)
    verify_present = verify_path.exists() and bool(verify)
    audit_freshness = _report_freshness(
        config.staging_dir,
        audit.get("artifact_fingerprints"),
        ["implementation_plan.json", "attack_module.py", "attack_catalog.yaml"],
    )
    verify_freshness = _report_freshness(
        config.staging_dir,
        verify.get("artifact_fingerprints"),
        ["implementation_plan.json", "attack_module.py", "attack_catalog.yaml"],
    )

    audit_verdict = str(audit.get("verdict") or "")
    verify_verdict = str(verify.get("verdict") or "")
    verify_ok = verify_verdict in {"pass", "pass_with_warnings"}
    family = str(manifest.get("family") or plan.get("family") or "").strip()
    execution_skeleton = str(
        manifest.get("forge_phase_b", {}).get("execution_skeleton") or ""
    )
    workflow_profile = str(
        manifest.get("forge_phase_b", {}).get("workflow_profile") or family or "generic"
    )
    promoted = bool(manifest.get("promotion_phase_g", {}).get("promoted"))

    missing_steps = _string_list(audit.get("step_coverage", {}).get("missing"))
    partial_steps = _string_list(audit.get("step_coverage", {}).get("partial"))
    generic_baseline_detected = bool(
        audit.get("module_checks", {}).get("generic_baseline_detected")
    )
    placeholder_markers = _string_list(audit.get("module_checks", {}).get("placeholder_markers"))
    benchmark_categories = set(_string_list(audit.get("categories")))
    supports_benchmark = bool(catalog.get("supports_benchmark"))
    catalog_mismatches = _string_list(audit.get("catalog_checks", {}).get("mismatches"))
    single_turn_report = verify.get("single_turn_checks", {})
    verify_categories = set(_string_list(verify.get("categories")))
    single_turn_checks = {
        "applicable": is_single_turn_family(family),
        "supported_skeleton": (
            is_supported_single_turn_skeleton(execution_skeleton)
            if is_single_turn_family(family)
            else True
        ),
        "workflow_profile_aligned": (
            workflow_profile == "single_turn"
            if is_single_turn_family(family)
            else True
        ),
        "verify_single_turn_ok": (
            bool(single_turn_report.get("ok"))
            if is_single_turn_family(family)
            else True
        ),
    }

    completion_checks = {
        "pipeline_complete": plan_present and forge_present and audit_present and verify_present,
        "runnable_draft_ready": forge_present and verify_ok,
        "review_ready": forge_present and audit_present and verify_ok,
        "promotion_ready": (
            verify_verdict == "pass"
            and audit_verdict == "pass_with_review"
            and audit_freshness["ok"]
            and verify_freshness["ok"]
            and not missing_steps
            and not partial_steps
            and not generic_baseline_detected
            and not placeholder_markers
            and not catalog_mismatches
            and not verify_categories
            and promoted is False
            and all(single_turn_checks.values())
        ),
        "benchmark_candidate": (
            verify_verdict == "pass"
            and audit_verdict == "pass_with_review"
            and audit_freshness["ok"]
            and verify_freshness["ok"]
            and not missing_steps
            and not partial_steps
            and not generic_baseline_detected
            and not placeholder_markers
            and not catalog_mismatches
            and supports_benchmark
            and "benchmark_not_advised" not in benchmark_categories
            and not verify_categories
            and promoted is False
            and all(single_turn_checks.values())
        ),
        "promoted": (
            promoted
            and all(single_turn_checks.values())
        ),
    }

    workflow_stage = _derive_workflow_stage(
        plan_present=plan_present,
        forge_present=forge_present,
        audit_present=audit_present,
        verify_present=verify_present,
        audit_verdict=audit_verdict,
        verify_verdict=verify_verdict,
        promoted=promoted,
        completion_checks=completion_checks,
    )
    forge_status = derive_forge_status(
        completion_checks=completion_checks,
        promoted=promoted,
    )
    current_report = {
        "workflow_stage": workflow_stage,
        "forge_status": forge_status,
        "completion_checks": completion_checks,
    }
    consistency_checks = build_consistency_checks(manifest, current_report)

    recommended_next_actions = _recommended_next_actions(
        plan_present=plan_present,
        forge_present=forge_present,
        audit_present=audit_present,
        verify_present=verify_present,
        promoted=promoted,
        audit_freshness=audit_freshness,
        verify_freshness=verify_freshness,
        family=family,
        execution_skeleton=execution_skeleton,
        audit=audit,
        verify=verify,
        completion_checks=completion_checks,
    )

    report = {
        "schema_version": WORKFLOW_STATUS_SCHEMA_VERSION,
        "attack_id": str(manifest.get("attack_id") or plan.get("attack_id") or config.attack_id),
        "workflow_stage": workflow_stage,
        "forge_status": forge_status,
        "workflow_profile": workflow_profile,
        "phase_presence": {
            "plan": plan_present,
            "forge": forge_present,
            "audit": audit_present,
            "verify": verify_present,
            "promote": promoted,
        },
        "completion_checks": completion_checks,
        "freshness_checks": {
            "audit": audit_freshness,
            "verify": verify_freshness,
        },
        "consistency_checks": consistency_checks,
        "profile_checks": {
            "single_turn": {
                **single_turn_checks,
                "supported_skeletons": list(SUPPORTED_SINGLE_TURN_SKELETONS),
            }
        },
        "phase_summaries": {
            "planner_backend_used": str(
                manifest.get("planner_phase_a", {}).get("planner_backend_used") or ""
            ),
            "forge_backend_used": str(
                manifest.get("forge_phase_b", {}).get("forge_backend_used") or ""
            ),
            "forge_status": forge_status,
            "execution_skeleton": str(
                manifest.get("forge_phase_b", {}).get("execution_skeleton") or ""
            ),
            "audit_verdict": audit_verdict,
            "verify_verdict": verify_verdict,
            "promoted_at": str(manifest.get("promotion_phase_g", {}).get("promoted_at") or ""),
        },
        "promotion_targets": manifest.get("promotion_targets", {}),
        "recommended_next_actions": recommended_next_actions,
    }
    return WorkflowStatusOutcome(
        workflow_status_text=_render_workflow_status_report(report),
        workflow_status=report,
    )


def _derive_workflow_stage(
    *,
    plan_present: bool,
    forge_present: bool,
    audit_present: bool,
    verify_present: bool,
    audit_verdict: str,
    verify_verdict: str,
    promoted: bool,
    completion_checks: dict[str, bool],
) -> str:
    if promoted or completion_checks["promoted"]:
        return WORKFLOW_STAGE_PROMOTED
    if completion_checks["benchmark_candidate"]:
        return WORKFLOW_STAGE_BENCHMARK_CANDIDATE
    if completion_checks["promotion_ready"]:
        return WORKFLOW_STAGE_PROMOTION_READY
    if verify_verdict == "blocked_by_verification_failure":
        return WORKFLOW_STAGE_VERIFICATION_BLOCKED
    if audit_verdict == "needs_refinement":
        return WORKFLOW_STAGE_NEEDS_REFINEMENT
    if completion_checks["review_ready"]:
        return WORKFLOW_STAGE_REVIEW_READY
    if forge_present and not audit_present:
        return WORKFLOW_STAGE_FORGED
    if plan_present and not forge_present:
        return WORKFLOW_STAGE_PLANNED
    if manifest_like_completed(plan_present, forge_present, audit_present, verify_present):
        return WORKFLOW_STAGE_REVIEW_READY
    if plan_present:
        return WORKFLOW_STAGE_SCAFFOLDED
    return WORKFLOW_STAGE_NOT_STARTED


def manifest_like_completed(
    plan_present: bool,
    forge_present: bool,
    audit_present: bool,
    verify_present: bool,
) -> bool:
    return plan_present and forge_present and audit_present and verify_present


def _recommended_next_actions(
    *,
    plan_present: bool,
    forge_present: bool,
    audit_present: bool,
    verify_present: bool,
    promoted: bool,
    audit_freshness: dict[str, Any],
    verify_freshness: dict[str, Any],
    family: str,
    execution_skeleton: str,
    audit: dict[str, Any],
    verify: dict[str, Any],
    completion_checks: dict[str, bool],
) -> list[str]:
    actions: list[str] = []
    if promoted:
        return ["Attack artifacts are promoted into PromptMap runtime paths."]
    if not plan_present:
        actions.append("Run `plan` to create implementation_plan.json and evidence artifacts.")
    if plan_present and not forge_present:
        actions.append("Run `forge` to generate attack_module.py and attack_catalog.yaml.")
    if forge_present and not audit_present:
        actions.append("Run `audit` to measure plan-to-code coverage.")
    if forge_present and not verify_present:
        actions.append("Run `verify` to validate importability and catalog schema.")

    if audit_present:
        for action in _string_list(audit.get("recommended_next_actions")):
            if action not in actions:
                actions.append(action)
    if verify_present:
        for action in _string_list(verify.get("recommended_next_actions")):
            if action not in actions:
                actions.append(action)

    if audit_present and not audit_freshness.get("ok"):
        actions.append("Re-run `audit` because staging artifacts changed after the current audit report.")
    if verify_present and not verify_freshness.get("ok"):
        actions.append("Re-run `verify` because staging artifacts changed after the current verification report.")
    if completion_checks["promotion_ready"]:
        actions.append("Run `promote` to copy the reviewed attack into `promptmap/attacks` and `promptmap/catalog/attacks`.")
    if completion_checks["promotion_ready"] and not completion_checks["benchmark_candidate"]:
        actions.append(
            "If this attack should enter benchmark lanes, enable supports_benchmark only after stable execution checks."
        )
    if is_single_turn_family(family):
        if not is_supported_single_turn_skeleton(execution_skeleton):
            actions.append(
                "Use one of the supported single-turn skeletons before calling this workflow single-turn complete."
            )
        if not bool(verify.get("single_turn_checks", {}).get("ok")):
            actions.append(
                "Resolve single-turn profile gaps reported by `verify` before promotion."
            )
    if not actions:
        actions.append("Workflow criteria are satisfied for the current staging target.")
    return actions


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _read_json_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_yaml_dict(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _report_freshness(
    staging_dir: Path,
    artifact_fingerprints: Any,
    required_files: list[str],
) -> dict[str, Any]:
    if not isinstance(artifact_fingerprints, dict) or not artifact_fingerprints:
        return {
            "ok": False,
            "missing_report_fingerprints": True,
            "mismatches": required_files,
        }
    mismatches: list[str] = []
    for filename in required_files:
        current_path = staging_dir / filename
        if not current_path.exists():
            mismatches.append(filename)
            continue
        expected = str(artifact_fingerprints.get(filename) or "").strip()
        current = hashlib.sha256(current_path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
        if not expected or expected != current:
            mismatches.append(filename)
    return {
        "ok": not mismatches,
        "missing_report_fingerprints": False,
        "mismatches": mismatches,
    }


def _render_workflow_status_report(report: dict[str, Any]) -> str:
    lines = [f"# Workflow Status: {report.get('attack_id', '')}", ""]
    lines.extend(
        [
            "## Stage",
            "",
            f"- `workflow_stage`: `{report.get('workflow_stage', '')}`",
            f"- `forge_status`: `{report.get('forge_status', '')}`",
            f"- `workflow_profile`: `{report.get('workflow_profile', '')}`",
            "",
            "## Phase Presence",
            "",
        ]
    )
    for key, value in report.get("phase_presence", {}).items():
        lines.append(f"- `{key}`: `{str(bool(value)).lower()}`")
    lines.extend(["", "## Completion Checks", ""])
    for key, value in report.get("completion_checks", {}).items():
        lines.append(f"- `{key}`: `{str(bool(value)).lower()}`")
    lines.extend(["", "## Freshness Checks", ""])
    for name, freshness in report.get("freshness_checks", {}).items():
        lines.append(f"### {name}")
        lines.append("")
        for key, value in freshness.items():
            if isinstance(value, bool):
                lines.append(f"- `{key}`: `{str(value).lower()}`")
            else:
                lines.append(f"- `{key}`: `{value}`")
        lines.append("")
    lines.extend(["", "## Consistency Checks", ""])
    for key, value in report.get("consistency_checks", {}).items():
        if isinstance(value, bool):
            lines.append(f"- `{key}`: `{str(value).lower()}`")
        else:
            lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Profile Checks", ""])
    for profile_name, checks in report.get("profile_checks", {}).items():
        lines.append(f"### {profile_name}")
        lines.append("")
        for key, value in checks.items():
            if isinstance(value, bool):
                lines.append(f"- `{key}`: `{str(value).lower()}`")
            else:
                lines.append(f"- `{key}`: `{value}`")
        lines.append("")
    lines.extend(["", "## Phase Summaries", ""])
    for key, value in report.get("phase_summaries", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.extend(["", "## Recommended Actions", ""])
    actions = report.get("recommended_next_actions") or []
    if not actions:
        lines.append("- none")
    else:
        for action in actions:
            lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)
