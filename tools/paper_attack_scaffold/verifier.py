from __future__ import annotations

import hashlib
import importlib.util
from dataclasses import dataclass
import json
from pathlib import Path
import py_compile
from typing import Any

import yaml

from promptmap.engine.base_attack import BaseAttack
from promptmap.registry.attack_spec import AttackSpec

from .common import normalize_attack_id, to_class_name


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

    reference_checks = _verify_reference_artifacts(
        reference_manifest=reference_manifest,
        reference_snippets_dir=reference_snippets_dir,
    )
    if not reference_checks["ok"]:
        categories.append("reference_artifact_mismatch")
        recommended_next_actions.append(
            "Repair reference_manifest.json / reference_snippets consistency."
        )

    if any(
        category in categories
        for category in (
            "plan_contract_invalid",
            "py_compile_failed",
            "module_import_smoke_failed",
            "catalog_schema_invalid",
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
        "plan_checks": plan_checks,
        "module_checks": {
            "py_compile_ok": py_compile_ok,
            "py_compile_error": py_compile_error,
            **import_smoke,
        },
        "catalog_checks": catalog_checks,
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


def _verify_module_import(
    *,
    module_path: Path,
    attack_id: str,
    expected_class_name: str,
) -> dict[str, Any]:
    module_name = f"_promptmap_scaffold_verify_{attack_id}"
    try:
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        if spec is None or spec.loader is None:
            return {
                "ok": False,
                "import_error": "Could not create import spec from staging module.",
                "class_name": expected_class_name,
                "is_base_attack_subclass": False,
            }
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls = getattr(module, expected_class_name, None)
        if not isinstance(cls, type):
            return {
                "ok": False,
                "import_error": f"Expected class '{expected_class_name}' not found.",
                "class_name": expected_class_name,
                "is_base_attack_subclass": False,
            }
        is_subclass = issubclass(cls, BaseAttack)
        return {
            "ok": is_subclass,
            "import_error": "" if is_subclass else f"{expected_class_name} is not a BaseAttack subclass.",
            "class_name": expected_class_name,
            "is_base_attack_subclass": is_subclass,
        }
    except Exception as exc:
        return {
            "ok": False,
            "import_error": f"{type(exc).__name__}: {exc}",
            "class_name": expected_class_name,
            "is_base_attack_subclass": False,
        }


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
    if report["module_checks"]["py_compile_error"]:
        lines.append(f"- `py_compile_error`: {report['module_checks']['py_compile_error']}")
    if report["module_checks"]["import_error"]:
        lines.append(f"- `import_error`: {report['module_checks']['import_error']}")
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
    lines.append("## Recommended Actions")
    lines.append("")
    for action in report["recommended_next_actions"] or ["No additional actions recorded."]:
        lines.append(f"- {action}")
    lines.append("")
    return "\n".join(lines)
