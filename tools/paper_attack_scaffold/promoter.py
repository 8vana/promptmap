from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import yaml

from .auditor import AuditConfig, run_audit
from .common import normalize_attack_id, write_text
from .lifecycle import FORGE_STATUS_PROMOTED, manifest_workflow_payload
from .quality import find_placeholder_markers, replace_forge_status
from .status import WorkflowStatusConfig, _render_workflow_status_report, run_workflow_status
from .verifier import VerifyConfig, run_verify


@dataclass(frozen=True)
class PromoteConfig:
    attack_id: str
    staging_dir: Path
    repo_root: Path
    force: bool = False


@dataclass(frozen=True)
class PromoteOutcome:
    attack_id: str
    attack_module_path: Path
    catalog_entry_path: Path
    promotion_record_path: Path
    workflow_status: dict[str, Any]


def run_promote(config: PromoteConfig) -> PromoteOutcome:
    manifest_path = config.staging_dir / "manifest.json"
    module_path = config.staging_dir / "attack_module.py"
    catalog_path = config.staging_dir / "attack_catalog.yaml"
    if not manifest_path.exists():
        raise ValueError(f"Missing manifest.json for promote: {manifest_path}")
    if not module_path.exists():
        raise ValueError(f"Missing attack_module.py for promote: {module_path}")
    if not catalog_path.exists():
        raise ValueError(f"Missing attack_catalog.yaml for promote: {catalog_path}")

    manifest = _read_json_dict(manifest_path)
    _refresh_review_artifacts(config.staging_dir, manifest)
    manifest = _read_json_dict(manifest_path)
    workflow = run_workflow_status(
        WorkflowStatusConfig(
            attack_id=normalize_attack_id(config.attack_id or str(manifest.get("attack_id") or config.staging_dir.name)),
            staging_dir=config.staging_dir,
        )
    ).workflow_status
    if not workflow.get("completion_checks", {}).get("promotion_ready"):
        raise ValueError(
            "Promote requires `promotion_ready=true`. "
            f"Current workflow_stage={workflow.get('workflow_stage', 'unknown')}."
        )

    module_source = module_path.read_text(encoding="utf-8")
    placeholder_markers = find_placeholder_markers(module_source)
    if placeholder_markers:
        raise ValueError(
            "Refusing to promote a module that still contains draft or placeholder markers: "
            + ", ".join(placeholder_markers)
        )

    catalog_data = _read_yaml_dict(catalog_path)
    promotion_targets = manifest.get("promotion_targets", {})
    attack_module_rel = str(
        promotion_targets.get("attack_module")
        or f"promptmap/attacks/{manifest.get('module_name') or config.staging_dir.name + '_attack'}.py"
    )
    catalog_entry_rel = str(
        promotion_targets.get("catalog_entry")
        or f"promptmap/catalog/attacks/{manifest.get('attack_id') or config.staging_dir.name}.yaml"
    )
    attack_module_dst = config.repo_root / attack_module_rel
    catalog_entry_dst = config.repo_root / catalog_entry_rel
    promotion_record_path = config.staging_dir / "promotion_record.json"

    _ensure_writable_destination(attack_module_dst, force=config.force)
    _ensure_writable_destination(catalog_entry_dst, force=config.force)

    promoted_module_source = replace_forge_status(module_source, FORGE_STATUS_PROMOTED)
    catalog_data["source_type"] = "builtin"
    attack_module_dst.parent.mkdir(parents=True, exist_ok=True)
    catalog_entry_dst.parent.mkdir(parents=True, exist_ok=True)
    write_text(attack_module_dst, promoted_module_source if promoted_module_source.endswith("\n") else promoted_module_source + "\n")
    write_text(
        catalog_entry_dst,
        yaml.safe_dump(catalog_data, sort_keys=False, allow_unicode=True).rstrip() + "\n",
    )

    timestamp = datetime.now(timezone.utc).isoformat()
    promotion_record = {
        "attack_id": manifest.get("attack_id") or config.attack_id,
        "promoted": True,
        "promoted_at": timestamp,
        "source_staging_dir": str(config.staging_dir),
        "workflow_stage_before_promote": workflow.get("workflow_stage", ""),
        "forge_status_before_promote": workflow.get("forge_status", ""),
        "attack_module_path": attack_module_rel,
        "catalog_entry_path": catalog_entry_rel,
        "audit_verdict": workflow.get("phase_summaries", {}).get("audit_verdict", ""),
        "verify_verdict": workflow.get("phase_summaries", {}).get("verify_verdict", ""),
    }
    write_text(
        promotion_record_path,
        json.dumps(promotion_record, indent=2, ensure_ascii=False) + "\n",
    )

    manifest["promotion_phase_g"] = {
        "promoted": True,
        "promoted_at": timestamp,
        "promotion_record_path": "promotion_record.json",
        "attack_module_path": attack_module_rel,
        "catalog_entry_path": catalog_entry_rel,
    }
    manifest.setdefault("forge_phase_b", {})
    if isinstance(manifest["forge_phase_b"], dict):
        manifest["forge_phase_b"]["forge_status"] = FORGE_STATUS_PROMOTED
    write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    promoted_workflow = run_workflow_status(
        WorkflowStatusConfig(
            attack_id=normalize_attack_id(config.attack_id or str(manifest.get("attack_id") or config.staging_dir.name)),
            staging_dir=config.staging_dir,
        )
    ).workflow_status
    write_text(
        config.staging_dir / "workflow_status.json",
        json.dumps(promoted_workflow, indent=2, ensure_ascii=False) + "\n",
    )
    write_text(
        config.staging_dir / "workflow_status.md",
        _render_workflow_status_report(promoted_workflow),
    )
    manifest = _read_json_dict(manifest_path)
    manifest["workflow_status_phase_f"] = manifest_workflow_payload(promoted_workflow)
    write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    return PromoteOutcome(
        attack_id=str(manifest.get("attack_id") or config.attack_id),
        attack_module_path=attack_module_dst,
        catalog_entry_path=catalog_entry_dst,
        promotion_record_path=promotion_record_path,
        workflow_status=promoted_workflow,
    )


def _ensure_writable_destination(path: Path, *, force: bool) -> None:
    if path.exists() and not force:
        raise ValueError(f"Refusing to overwrite existing promoted file: {path}. Use --force to overwrite.")


def _refresh_review_artifacts(staging_dir: Path, manifest: dict[str, Any]) -> None:
    attack_id = normalize_attack_id(str(manifest.get("attack_id") or staging_dir.name))
    audit_outcome = run_audit(AuditConfig(attack_id=attack_id, staging_dir=staging_dir))
    write_text(
        staging_dir / "audit_verdict.json",
        json.dumps(audit_outcome.audit_verdict, indent=2, ensure_ascii=False) + "\n",
    )
    write_text(staging_dir / "coverage_report.md", audit_outcome.coverage_report_text)
    write_text(staging_dir / "review_checklist.md", audit_outcome.review_checklist_text)

    verify_outcome = run_verify(VerifyConfig(attack_id=attack_id, staging_dir=staging_dir))
    write_text(
        staging_dir / "verification_report.json",
        json.dumps(verify_outcome.verification_report, indent=2, ensure_ascii=False) + "\n",
    )
    write_text(staging_dir / "verification_report.md", verify_outcome.verification_report_text)

    manifest = _read_json_dict(staging_dir / "manifest.json")
    manifest["audit_phase_c"] = {
        "coverage_report_path": "coverage_report.md",
        "audit_verdict_path": "audit_verdict.json",
        "review_checklist_path": "review_checklist.md",
        "verdict": audit_outcome.audit_verdict.get("verdict", ""),
        "categories": audit_outcome.audit_verdict.get("categories", []),
    }
    manifest["verification_phase_e"] = {
        "verification_report_md_path": "verification_report.md",
        "verification_report_json_path": "verification_report.json",
        "verdict": verify_outcome.verification_report.get("verdict", ""),
        "categories": verify_outcome.verification_report.get("categories", []),
    }
    write_text(staging_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")


def _read_json_dict(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _read_yaml_dict(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}
