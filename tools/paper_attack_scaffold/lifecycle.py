from __future__ import annotations

from typing import Any

FORGE_STATUS_DRAFT = "draft"
FORGE_STATUS_REVIEW_READY = "review_ready"
FORGE_STATUS_PRODUCTION_READY = "production_ready"
FORGE_STATUS_PROMOTED = "promoted"

WORKFLOW_STAGE_NOT_STARTED = "not_started"
WORKFLOW_STAGE_SCAFFOLDED = "scaffolded"
WORKFLOW_STAGE_PLANNED = "planned"
WORKFLOW_STAGE_FORGED = "forged"
WORKFLOW_STAGE_REVIEW_READY = "review_ready"
WORKFLOW_STAGE_NEEDS_REFINEMENT = "needs_refinement"
WORKFLOW_STAGE_VERIFICATION_BLOCKED = "verification_blocked"
WORKFLOW_STAGE_PROMOTION_READY = "promotion_ready"
WORKFLOW_STAGE_BENCHMARK_CANDIDATE = "benchmark_candidate"
WORKFLOW_STAGE_PROMOTED = "promoted"

WORKFLOW_STATUS_SCHEMA_VERSION = 2


def derive_forge_status(
    *,
    completion_checks: dict[str, bool],
    promoted: bool,
) -> str:
    if promoted or completion_checks.get("promoted"):
        return FORGE_STATUS_PROMOTED
    if completion_checks.get("promotion_ready") or completion_checks.get("benchmark_candidate"):
        return FORGE_STATUS_PRODUCTION_READY
    if completion_checks.get("review_ready"):
        return FORGE_STATUS_REVIEW_READY
    return FORGE_STATUS_DRAFT


def manifest_workflow_payload(report: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": WORKFLOW_STATUS_SCHEMA_VERSION,
        "workflow_status_md_path": "workflow_status.md",
        "workflow_status_json_path": "workflow_status.json",
        "workflow_stage": report.get("workflow_stage", ""),
        "forge_status": report.get("forge_status", ""),
        "completion_checks": report.get("completion_checks", {}),
        "consistency_checks": report.get("consistency_checks", {}),
    }


def build_consistency_checks(
    manifest: dict[str, Any],
    current_report: dict[str, Any],
) -> dict[str, Any]:
    snapshot = manifest.get("workflow_status_phase_f", {})
    if not isinstance(snapshot, dict) or not snapshot:
        return {
            "manifest_snapshot_present": False,
            "manifest_snapshot_matches": True,
            "mismatches": [],
        }

    mismatches: list[str] = []
    if str(snapshot.get("workflow_stage") or "") != str(current_report.get("workflow_stage") or ""):
        mismatches.append("workflow_stage")
    if str(snapshot.get("forge_status") or "") != str(current_report.get("forge_status") or ""):
        mismatches.append("forge_status")
    snapshot_checks = snapshot.get("completion_checks", {})
    current_checks = current_report.get("completion_checks", {})
    if isinstance(snapshot_checks, dict):
        for key, value in current_checks.items():
            if bool(snapshot_checks.get(key)) != bool(value):
                mismatches.append(f"completion_checks.{key}")
    else:
        mismatches.append("completion_checks")

    return {
        "manifest_snapshot_present": True,
        "manifest_snapshot_matches": not mismatches,
        "mismatches": mismatches,
    }
