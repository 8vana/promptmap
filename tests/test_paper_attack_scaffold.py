from __future__ import annotations

import json
from pathlib import Path
import shutil
import tempfile
import unittest

import yaml

from tools.paper_attack_scaffold.auditor import AuditConfig, run_audit
from tools.paper_attack_scaffold.promoter import PromoteConfig, run_promote
from tools.paper_attack_scaffold.status import WorkflowStatusConfig, run_workflow_status
from tools.paper_attack_scaffold.verifier import VerifyConfig, run_verify


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_ROOT = REPO_ROOT / "staging" / "attacks"


class PaperAttackScaffoldWorkflowTests(unittest.TestCase):
    def test_draft_fixture_requires_refinement(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_dir = _copy_fixture("radial", Path(tmpdir))
            audit = _write_audit(staging_dir)
            verify = _write_verify(staging_dir)
            status = run_workflow_status(
                WorkflowStatusConfig(attack_id="radial", staging_dir=staging_dir)
            ).workflow_status

            self.assertEqual(audit["verdict"], "needs_refinement")
            self.assertIn("draft_artifact_detected", audit["categories"])
            self.assertIn("placeholder_logic_detected", audit["categories"])
            self.assertEqual(verify["verdict"], "pass_with_warnings")
            self.assertIn("draft_artifact_detected", verify["categories"])
            self.assertEqual(status["workflow_stage"], "needs_refinement")
            self.assertEqual(status["forge_status"], "review_ready")

    def test_status_reports_consistency_mismatches_for_stale_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            staging_dir = _copy_fixture("radial_e2e", Path(tmpdir))
            manifest_path = staging_dir / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["workflow_status_phase_f"] = {
                "workflow_stage": "planned",
                "forge_status": "draft",
                "completion_checks": {"promotion_ready": False},
            }
            manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

            _write_audit(staging_dir)
            _write_verify(staging_dir)
            status = run_workflow_status(
                WorkflowStatusConfig(attack_id="radial_e2e", staging_dir=staging_dir)
            ).workflow_status

            self.assertTrue(status["completion_checks"]["promotion_ready"])
            self.assertEqual(status["forge_status"], "production_ready")
            self.assertFalse(status["consistency_checks"]["manifest_snapshot_matches"])
            self.assertIn("workflow_stage", status["consistency_checks"]["mismatches"])
            self.assertIn("forge_status", status["consistency_checks"]["mismatches"])

    def test_promote_copies_runtime_artifacts_and_updates_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "promptmap" / "attacks").mkdir(parents=True, exist_ok=True)
            (repo_root / "promptmap" / "catalog" / "attacks").mkdir(parents=True, exist_ok=True)
            staging_dir = _copy_fixture("radial_e2e", repo_root / "staging" / "attacks")

            _write_audit(staging_dir)
            _write_verify(staging_dir)
            outcome = run_promote(
                PromoteConfig(
                    attack_id="radial_e2e",
                    staging_dir=staging_dir,
                    repo_root=repo_root,
                    force=True,
                )
            )

            promoted_module = outcome.attack_module_path.read_text(encoding="utf-8")
            promoted_catalog = yaml.safe_load(outcome.catalog_entry_path.read_text(encoding="utf-8"))
            manifest = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))

            self.assertIn('"forge_status": "promoted"', promoted_module)
            self.assertEqual(promoted_catalog["source_type"], "builtin")
            self.assertTrue(manifest["promotion_phase_g"]["promoted"])
            self.assertEqual(outcome.workflow_status["workflow_stage"], "promoted")
            self.assertEqual(outcome.workflow_status["forge_status"], "promoted")

    def test_stale_reports_block_promotion_until_reverified(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_root = Path(tmpdir)
            (repo_root / "promptmap" / "attacks").mkdir(parents=True, exist_ok=True)
            (repo_root / "promptmap" / "catalog" / "attacks").mkdir(parents=True, exist_ok=True)
            staging_dir = _copy_fixture("radial_e2e", repo_root / "staging" / "attacks")

            _write_audit(staging_dir)
            _write_verify(staging_dir)
            module_path = staging_dir / "attack_module.py"
            module_path.write_text(
                module_path.read_text(encoding="utf-8") + "\n# TODO(late_change): stale report guard\n",
                encoding="utf-8",
            )

            status = run_workflow_status(
                WorkflowStatusConfig(attack_id="radial_e2e", staging_dir=staging_dir)
            ).workflow_status

            self.assertFalse(status["freshness_checks"]["audit"]["ok"])
            self.assertFalse(status["freshness_checks"]["verify"]["ok"])
            self.assertFalse(status["completion_checks"]["promotion_ready"])
            self.assertIn(
                "Re-run `audit` because staging artifacts changed after the current audit report.",
                status["recommended_next_actions"],
            )

            with self.assertRaises(ValueError):
                run_promote(
                    PromoteConfig(
                        attack_id="radial_e2e",
                        staging_dir=staging_dir,
                        repo_root=repo_root,
                        force=True,
                    )
                )


def _copy_fixture(name: str, target_root: Path) -> Path:
    target_root.mkdir(parents=True, exist_ok=True)
    staging_dir = target_root / name
    shutil.copytree(FIXTURE_ROOT / name, staging_dir)
    return staging_dir


def _write_audit(staging_dir: Path) -> dict:
    outcome = run_audit(AuditConfig(attack_id=staging_dir.name, staging_dir=staging_dir))
    (staging_dir / "audit_verdict.json").write_text(
        json.dumps(outcome.audit_verdict, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (staging_dir / "coverage_report.md").write_text(
        outcome.coverage_report_text,
        encoding="utf-8",
    )
    (staging_dir / "review_checklist.md").write_text(
        outcome.review_checklist_text,
        encoding="utf-8",
    )
    return outcome.audit_verdict


def _write_verify(staging_dir: Path) -> dict:
    outcome = run_verify(VerifyConfig(attack_id=staging_dir.name, staging_dir=staging_dir))
    (staging_dir / "verification_report.json").write_text(
        json.dumps(outcome.verification_report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (staging_dir / "verification_report.md").write_text(
        outcome.verification_report_text,
        encoding="utf-8",
    )
    return outcome.verification_report


if __name__ == "__main__":
    unittest.main()
