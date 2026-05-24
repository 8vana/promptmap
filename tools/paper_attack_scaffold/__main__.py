from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .common import (
    VALID_FAMILIES,
    VALID_TARGET_MODES,
    bullet_block,
    ensure_file_overwrite_allowed,
    parse_csv,
    parse_params,
    render_template,
    to_class_name,
    to_registered_name,
    write_text,
    yaml_inline,
    yaml_inline_or_mapping,
    yaml_scalar,
    normalize_attack_id,
)
from .auditor import AuditConfig, run_audit
from .forger import ForgeConfig, build_forge_artifacts
from .ingest import ingest_inputs
from .planner import PlannerConfig, build_plan, render_plan_markdown
from .repo_ingest import (
    ingest_reference_repository,
    normalize_repo_url,
    normalize_selected_paths,
    write_reference_artifacts,
)
from .status import WorkflowStatusConfig, run_workflow_status
from .verifier import VerifyConfig, run_verify


def main(argv: list[str] | None = None) -> None:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] not in {"scaffold", "plan", "forge", "audit", "verify", "status", "-h", "--help"}:
        argv = ["scaffold", *argv]
    if not argv:
        argv = ["-h"]

    parser = argparse.ArgumentParser(
        prog="python -m tools.paper_attack_scaffold",
        description="Generate PromptMap staging artifacts for research attacks.",
    )
    subparsers = parser.add_subparsers(dest="command")
    _build_scaffold_parser(subparsers.add_parser("scaffold", help="Generate a metadata-only scaffold."))
    _build_plan_parser(subparsers.add_parser("plan", help="Create an implementation plan from paper material."))
    _build_forge_parser(subparsers.add_parser("forge", help="Generate plan-driven draft artifacts from an implementation plan."))
    _build_audit_parser(subparsers.add_parser("audit", help="Audit plan-to-code coverage for a staging directory."))
    _build_verify_parser(subparsers.add_parser("verify", help="Run promotion-oriented local verification checks for a staging directory."))
    _build_status_parser(subparsers.add_parser("status", help="Summarize workflow readiness and next actions for a staging directory."))

    args = parser.parse_args(argv)
    if args.command == "scaffold":
        _run_scaffold(args, parser)
        return
    if args.command == "plan":
        _run_plan(args, parser)
        return
    if args.command == "forge":
        _run_forge(args, parser)
        return
    if args.command == "audit":
        _run_audit(args, parser)
        return
    if args.command == "verify":
        _run_verify(args, parser)
        return
    if args.command == "status":
        _run_status(args, parser)
        return
    parser.print_help()


def _build_scaffold_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attack-id", required=True, help="Stable runtime id, e.g. skeleton_key.")
    parser.add_argument("--display-name", required=True, help="User-facing attack display name.")
    parser.add_argument("--family", required=True, choices=sorted(VALID_FAMILIES))
    parser.add_argument("--description", default="", help="Short catalog description.")
    parser.add_argument("--paper-title", default="", help="Paper title.")
    parser.add_argument("--paper-url", default="", help="Paper URL.")
    parser.add_argument("--paper-year", type=int, default=None, help="Paper publication year.")
    parser.add_argument("--source-type", default="generated", help="Catalog source_type. Defaults to 'generated'.")
    parser.add_argument("--prompt-technique-aware", action="store_true",
                        help="Mark the scaffold as accepting prompt_technique in run(...).")
    parser.add_argument("--supports-benchmark", action="store_true",
                        help="Mark the scaffold benchmarkable. Off by default until reviewed.")
    parser.add_argument("--target-modes", default="api",
                        help="Comma-separated target modes. Default: api")
    parser.add_argument("--required-capabilities", default="scorer_llm",
                        help="Comma-separated capability tags. Default: scorer_llm")
    parser.add_argument("--tags", default="generated,research",
                        help="Comma-separated tags.")
    parser.add_argument("--compatible-atlas-techniques", default="",
                        help="Comma-separated MITRE ATLAS technique ids.")
    parser.add_argument("--default-param", action="append", default=[],
                        help="Repeatable KEY=VALUE entries for default_params.")
    parser.add_argument("--benchmark-param", action="append", default=[],
                        help="Repeatable KEY=VALUE entries for benchmark_defaults.")
    parser.add_argument("--output-dir", default="staging/attacks",
                        help="Staging root directory. Default: staging/attacks")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite an existing staging directory.")


def _build_plan_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attack-id", default=None, help="Optional attack id override.")
    parser.add_argument("--display-name", default=None, help="Optional display name override.")
    parser.add_argument("--family", default=None, choices=sorted(VALID_FAMILIES),
                        help="Optional family hint.")
    parser.add_argument("--paper-title", default=None, help="Optional paper title override.")
    parser.add_argument("--paper-url", default=None, help="Paper URL for provenance.")
    parser.add_argument("--paper-text-path", default=None,
                        help="Local markdown or plaintext file for planner input.")
    parser.add_argument("--pdf-path", default=None,
                        help="Local PDF file. Uses Docling to create normalized paper.md / paper.json.")
    parser.add_argument("--notes-path", default=None,
                        help="Optional operator notes file.")
    parser.add_argument("--reference-repo-url", default=None,
                        help="Optional supplementary GitHub repository URL.")
    parser.add_argument("--reference-path", action="append", default=[],
                        help="Repeatable repo-relative path to a supplementary file.")
    parser.add_argument("--reference-branch", default=None,
                        help="Optional branch for GitHub raw fetch mode.")
    parser.add_argument("--reference-root", default=None,
                        help="Optional local supplementary repo root for selected reference paths.")
    parser.add_argument("--provider", default=None,
                        help="Optional LLM provider for planner refinement.")
    parser.add_argument("--model", default=None,
                        help="Optional LLM model for planner refinement.")
    parser.add_argument("--planner-backend", default="auto", choices=["auto", "heuristic", "llm"],
                        help="Planner mode. 'auto' uses LLM when configured, else heuristic.")
    parser.add_argument("--output-dir", default="staging/attacks",
                        help="Staging root directory. Default: staging/attacks")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing plan artifacts if present.")


def _build_forge_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attack-id", default=None, help="Attack id used to resolve the staging directory.")
    parser.add_argument("--staging-dir", default=None,
                        help="Optional direct path to a staging directory containing implementation_plan.json.")
    parser.add_argument("--output-dir", default="staging/attacks",
                        help="Staging root when --staging-dir is not supplied. Default: staging/attacks")
    parser.add_argument("--provider", default=None,
                        help="Optional LLM provider for LLM-assisted forge.")
    parser.add_argument("--model", default=None,
                        help="Optional LLM model for LLM-assisted forge.")
    parser.add_argument("--forge-backend", default="heuristic", choices=["heuristic", "llm", "auto"],
                        help="Forge mode. 'auto' uses LLM when configured, else heuristic.")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing forge artifacts if present.")


def _build_audit_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attack-id", default=None, help="Attack id used to resolve the staging directory.")
    parser.add_argument("--staging-dir", default=None,
                        help="Optional direct path to a staging directory containing implementation_plan.json and attack_module.py.")
    parser.add_argument("--output-dir", default="staging/attacks",
                        help="Staging root when --staging-dir is not supplied. Default: staging/attacks")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing audit artifacts if present.")


def _build_verify_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attack-id", default=None, help="Attack id used to resolve the staging directory.")
    parser.add_argument("--staging-dir", default=None,
                        help="Optional direct path to a staging directory containing implementation_plan.json, attack_module.py, and attack_catalog.yaml.")
    parser.add_argument("--output-dir", default="staging/attacks",
                        help="Staging root when --staging-dir is not supplied. Default: staging/attacks")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing verification artifacts if present.")


def _build_status_parser(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--attack-id", default=None, help="Attack id used to resolve the staging directory.")
    parser.add_argument("--staging-dir", default=None,
                        help="Optional direct path to a staging directory to summarize.")
    parser.add_argument("--output-dir", default="staging/attacks",
                        help="Staging root when --staging-dir is not supplied. Default: staging/attacks")
    parser.add_argument("--force", action="store_true",
                        help="Overwrite existing workflow status artifacts if present.")


def _run_scaffold(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        attack_id = normalize_attack_id(args.attack_id)
        target_modes = parse_csv(args.target_modes)
        required_capabilities = parse_csv(args.required_capabilities)
        tags = parse_csv(args.tags)
        compatible_atlas_techniques = parse_csv(args.compatible_atlas_techniques)
        default_params = parse_params(args.default_param)
        benchmark_defaults = parse_params(args.benchmark_param)
    except ValueError as exc:
        parser.error(str(exc))

    unknown_target_modes = sorted(set(target_modes) - VALID_TARGET_MODES)
    if unknown_target_modes:
        parser.error(
            f"Unknown target modes {unknown_target_modes}. Allowed: {sorted(VALID_TARGET_MODES)}"
        )

    module_name = f"{attack_id}_attack"
    class_name = to_class_name(attack_id)
    registered_name = to_registered_name(attack_id, args.family)
    description = args.description or f"Scaffold for the research attack '{args.display_name}'."

    staging_dir = Path(args.output_dir) / attack_id
    if staging_dir.exists() and not args.force:
        parser.error(
            f"Staging directory already exists: {staging_dir}. Use --force to overwrite."
        )
    staging_dir.mkdir(parents=True, exist_ok=True)

    context = {
        "attack_id": attack_id,
        "attack_id_yaml": yaml_scalar(attack_id),
        "display_name": args.display_name,
        "display_name_yaml": yaml_scalar(args.display_name),
        "family": args.family,
        "family_yaml": yaml_scalar(args.family),
        "description": description,
        "description_yaml": yaml_scalar(description),
        "paper_title": args.paper_title,
        "paper_title_yaml": yaml_scalar(args.paper_title),
        "paper_url": args.paper_url,
        "paper_url_yaml": yaml_scalar(args.paper_url),
        "paper_year_yaml": yaml_scalar(args.paper_year),
        "paper_title_or_tbd": args.paper_title or "TBD",
        "paper_url_or_tbd": args.paper_url or "TBD",
        "paper_title_repr": repr(args.paper_title),
        "paper_url_repr": repr(args.paper_url),
        "source_type": args.source_type,
        "source_type_yaml": yaml_scalar(args.source_type),
        "prompt_technique_aware": yaml_scalar(args.prompt_technique_aware),
        "prompt_technique_aware_display": str(args.prompt_technique_aware).lower(),
        "supports_benchmark": yaml_scalar(args.supports_benchmark),
        "supports_benchmark_display": str(args.supports_benchmark).lower(),
        "target_modes_yaml": yaml_inline(target_modes),
        "required_capabilities_yaml": yaml_inline(required_capabilities),
        "tags_yaml": yaml_inline(tags),
        "default_params_yaml": yaml_inline_or_mapping(default_params),
        "benchmark_defaults_yaml": yaml_inline_or_mapping(benchmark_defaults),
        "compatible_atlas_techniques_yaml": yaml_inline(compatible_atlas_techniques),
        "required_capabilities_bullets": bullet_block(required_capabilities),
        "target_modes_bullets": bullet_block(target_modes),
        "module_name": module_name,
        "class_name": class_name,
        "registered_name": registered_name,
        "registered_name_yaml": yaml_scalar(registered_name),
    }

    write_text(staging_dir / "attack_module.py", render_template("attack_module.py.j2", context))
    write_text(staging_dir / "attack_catalog.yaml", render_template("attack_catalog.yaml.j2", context))
    write_text(staging_dir / "review_checklist.md", render_template("review_checklist.md.j2", context))
    write_text(staging_dir / "benchmark_notes.md", render_template("benchmark_notes.md.j2", context))
    manifest = {
        "attack_id": attack_id,
        "display_name": args.display_name,
        "family": args.family,
        "module_name": module_name,
        "class_name": class_name,
        "registered_name": registered_name,
        "staging_dir": str(staging_dir),
        "promotion_targets": {
            "attack_module": f"promptmap/attacks/{module_name}.py",
            "catalog_entry": f"promptmap/catalog/attacks/{attack_id}.yaml",
        },
    }
    write_text(staging_dir / "manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(staging_dir)


def _run_plan(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    try:
        reference_config = _normalize_reference_inputs(args)
    except ValueError as exc:
        parser.error(str(exc))

    reference_bundle = None
    if reference_config["reference_backend_requested"]:
        try:
            reference_bundle = ingest_reference_repository(
                reference_repo_url=str(reference_config["reference_repo_url"] or ""),
                reference_paths=list(reference_config["reference_paths"]),
                reference_branch=str(reference_config["reference_branch"] or ""),
                reference_root=str(reference_config["reference_root"] or ""),
            )
        except Exception as exc:
            parser.error(str(exc))

    try:
        ingest = ingest_inputs(
            paper_text_path=args.paper_text_path,
            pdf_path=args.pdf_path,
            notes_path=args.notes_path,
            paper_url=args.paper_url,
        )
    except Exception as exc:
        parser.error(str(exc))

    attack_id = normalize_attack_id(
        args.attack_id or _fallback_attack_id(args.paper_title, args.paper_text_path, args.pdf_path)
    )
    staging_dir = Path(args.output_dir) / attack_id
    try:
        ensure_file_overwrite_allowed(
            staging_dir,
            [
                "paper.md",
                "paper.json",
                "input_manifest.json",
                "implementation_plan.json",
                "implementation_plan.md",
                "raw_planner_output.json",
                "raw_planner_response.txt",
                "reference_manifest.json",
            ],
            force=args.force,
        )
    except ValueError as exc:
        parser.error(str(exc))

    if reference_bundle is not None:
        try:
            ensure_file_overwrite_allowed(
                staging_dir / "reference_snippets",
                [snippet.snippet_filename for snippet in reference_bundle.snippets],
                force=args.force,
            )
        except ValueError as exc:
            parser.error(str(exc))

    outcome = build_plan(
        config=PlannerConfig(
            attack_id=attack_id,
            display_name=args.display_name,
            family=args.family,
            paper_title=args.paper_title,
            paper_url=args.paper_url,
            provider=args.provider,
            model=args.model,
            planner_backend=args.planner_backend,
        ),
        paper_markdown=ingest.markdown,
        notes_text=ingest.notes_text,
        repo_snippets=reference_bundle.snippets if reference_bundle is not None else [],
    )
    plan = outcome.plan

    write_text(staging_dir / "paper.md", ingest.markdown)
    write_text(
        staging_dir / "paper.json",
        json.dumps(ingest.structured_paper, indent=2, ensure_ascii=False) + "\n",
    )
    write_text(
        staging_dir / "input_manifest.json",
        json.dumps(
            {
                **ingest.input_manifest,
                "reference_repo_url": reference_config["reference_repo_url"],
                "reference_paths": reference_config["reference_paths"],
                "reference_branch": reference_config["reference_branch"],
                "reference_root": reference_config["reference_root"],
                "reference_backend_requested": reference_config["reference_backend_requested"],
                "reference_manifest_path": "reference_manifest.json" if reference_bundle is not None else "",
                "reference_snippets_dir": "reference_snippets" if reference_bundle is not None else "",
                "reference_snippet_count": len(reference_bundle.snippets) if reference_bundle is not None else 0,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
    )
    write_text(
        staging_dir / "implementation_plan.json",
        json.dumps(plan.to_dict(), indent=2, ensure_ascii=False) + "\n",
    )
    write_text(staging_dir / "implementation_plan.md", render_plan_markdown(plan))
    if outcome.raw_payload is not None:
        write_text(
            staging_dir / "raw_planner_output.json",
            json.dumps(outcome.raw_payload, indent=2, ensure_ascii=False) + "\n",
        )
        write_text(
            staging_dir / "raw_planner_response.txt",
            outcome.raw_response_text.rstrip() + "\n",
        )
    if reference_bundle is not None:
        write_reference_artifacts(staging_dir, reference_bundle)

    existing_manifest = _load_existing_manifest(staging_dir / "manifest.json")
    existing_manifest.setdefault("attack_id", plan.attack_id)
    existing_manifest.setdefault("display_name", plan.display_name)
    existing_manifest.setdefault("staging_dir", str(staging_dir))
    existing_manifest["planner_phase_a"] = {
        "planner_backend_used": outcome.planner_backend_used,
        "planner_backend_requested": args.planner_backend,
        "provider": args.provider or "",
        "model": args.model or "",
        "paper_title": plan.paper_title,
        "paper_url": plan.paper_url,
        "input_manifest_path": "input_manifest.json",
        "implementation_plan_json_path": "implementation_plan.json",
        "implementation_plan_md_path": "implementation_plan.md",
        "paper_markdown_path": "paper.md",
        "paper_json_path": "paper.json",
        "planner_excerpt_chars": len(outcome.planner_excerpt),
        "raw_planner_output_path": "raw_planner_output.json" if outcome.raw_payload is not None else "",
        "raw_planner_response_path": "raw_planner_response.txt" if outcome.raw_payload is not None else "",
        "reference_repo_url": reference_config["reference_repo_url"],
        "reference_paths": reference_config["reference_paths"],
        "reference_branch": reference_config["reference_branch"],
        "reference_root": reference_config["reference_root"],
        "reference_backend_requested": reference_config["reference_backend_requested"],
        "reference_manifest_path": "reference_manifest.json" if reference_bundle is not None else "",
        "reference_snippets_dir": "reference_snippets" if reference_bundle is not None else "",
        "reference_snippet_count": len(reference_bundle.snippets) if reference_bundle is not None else 0,
    }
    write_text(
        staging_dir / "manifest.json",
        json.dumps(existing_manifest, indent=2, ensure_ascii=False) + "\n",
    )
    print(staging_dir)


def _run_forge(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not args.staging_dir and not args.attack_id:
        parser.error("forge requires either --staging-dir or --attack-id")

    if args.staging_dir:
        staging_dir = Path(args.staging_dir)
        attack_id = normalize_attack_id(args.attack_id or staging_dir.name)
    else:
        attack_id = normalize_attack_id(args.attack_id)
        staging_dir = Path(args.output_dir) / attack_id

    plan_path = staging_dir / "implementation_plan.json"
    if not plan_path.exists():
        parser.error(f"Missing implementation plan: {plan_path}")

    try:
        ensure_file_overwrite_allowed(
            staging_dir,
            [
                "attack_module.py",
                "attack_catalog.yaml",
                "benchmark_notes.md",
                "review_checklist.md",
                "generation_notes.md",
                "raw_forge_output.json",
                "raw_forge_response.txt",
            ],
            force=args.force,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        outcome = build_forge_artifacts(
            ForgeConfig(
                attack_id=attack_id,
                staging_dir=staging_dir,
                provider=args.provider,
                model=args.model,
                forge_backend=args.forge_backend,
            )
        )
    except ValueError as exc:
        parser.error(str(exc))

    write_text(staging_dir / "attack_module.py", outcome.attack_module_text)
    write_text(staging_dir / "attack_catalog.yaml", outcome.attack_catalog_text)
    write_text(staging_dir / "benchmark_notes.md", outcome.benchmark_notes_text)
    write_text(staging_dir / "review_checklist.md", outcome.review_checklist_text)
    write_text(staging_dir / "generation_notes.md", outcome.generation_notes_text)
    if outcome.raw_payload is not None:
        write_text(
            staging_dir / "raw_forge_output.json",
            json.dumps(outcome.raw_payload, indent=2, ensure_ascii=False) + "\n",
        )
        write_text(
            staging_dir / "raw_forge_response.txt",
            outcome.raw_response_text.rstrip() + "\n",
        )

    existing_manifest = _load_existing_manifest(staging_dir / "manifest.json")
    existing_manifest["attack_id"] = outcome.attack_id
    existing_manifest["display_name"] = outcome.display_name
    existing_manifest["family"] = outcome.family
    existing_manifest["module_name"] = outcome.module_name
    existing_manifest["class_name"] = outcome.class_name
    existing_manifest["registered_name"] = outcome.registered_name
    existing_manifest.setdefault("staging_dir", str(staging_dir))
    existing_manifest["promotion_targets"] = {
        "attack_module": f"promptmap/attacks/{outcome.module_name}.py",
        "catalog_entry": f"promptmap/catalog/attacks/{outcome.attack_id}.yaml",
    }
    existing_manifest["forge_phase_b"] = {
        "forge_backend_used": outcome.forge_backend_used,
        "forge_backend_requested": args.forge_backend,
        "provider": args.provider or "",
        "model": args.model or "",
        "execution_skeleton": outcome.execution_skeleton,
        "classification_signals": outcome.classification_signals,
        "workflow_profile": outcome.workflow_profile,
        "implementation_plan_json_path": "implementation_plan.json",
        "attack_module_path": "attack_module.py",
        "attack_catalog_path": "attack_catalog.yaml",
        "benchmark_notes_path": "benchmark_notes.md",
        "review_checklist_path": "review_checklist.md",
        "generation_notes_path": "generation_notes.md",
        "py_compile_ok": outcome.py_compile_ok,
        "raw_forge_output_path": "raw_forge_output.json" if outcome.raw_payload is not None else "",
        "raw_forge_response_path": "raw_forge_response.txt" if outcome.raw_payload is not None else "",
    }
    write_text(
        staging_dir / "manifest.json",
        json.dumps(existing_manifest, indent=2, ensure_ascii=False) + "\n",
    )
    print(staging_dir)


def _run_audit(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not args.staging_dir and not args.attack_id:
        parser.error("audit requires either --staging-dir or --attack-id")

    if args.staging_dir:
        staging_dir = Path(args.staging_dir)
        attack_id = normalize_attack_id(args.attack_id or staging_dir.name)
    else:
        attack_id = normalize_attack_id(args.attack_id)
        staging_dir = Path(args.output_dir) / attack_id

    try:
        ensure_file_overwrite_allowed(
            staging_dir,
            [
                "coverage_report.md",
                "audit_verdict.json",
                "review_checklist.md",
            ],
            force=args.force,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        outcome = run_audit(
            AuditConfig(
                attack_id=attack_id,
                staging_dir=staging_dir,
            )
        )
    except ValueError as exc:
        parser.error(str(exc))

    write_text(staging_dir / "coverage_report.md", outcome.coverage_report_text)
    write_text(
        staging_dir / "audit_verdict.json",
        json.dumps(outcome.audit_verdict, indent=2, ensure_ascii=False) + "\n",
    )
    write_text(staging_dir / "review_checklist.md", outcome.review_checklist_text)

    existing_manifest = _load_existing_manifest(staging_dir / "manifest.json")
    existing_manifest.setdefault("attack_id", attack_id)
    existing_manifest.setdefault("staging_dir", str(staging_dir))
    existing_manifest["audit_phase_c"] = {
        "coverage_report_path": "coverage_report.md",
        "audit_verdict_path": "audit_verdict.json",
        "review_checklist_path": "review_checklist.md",
        "verdict": outcome.audit_verdict.get("verdict", ""),
        "categories": outcome.audit_verdict.get("categories", []),
    }
    write_text(
        staging_dir / "manifest.json",
        json.dumps(existing_manifest, indent=2, ensure_ascii=False) + "\n",
    )
    print(staging_dir)


def _run_verify(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not args.staging_dir and not args.attack_id:
        parser.error("verify requires either --staging-dir or --attack-id")

    if args.staging_dir:
        staging_dir = Path(args.staging_dir)
        attack_id = normalize_attack_id(args.attack_id or staging_dir.name)
    else:
        attack_id = normalize_attack_id(args.attack_id)
        staging_dir = Path(args.output_dir) / attack_id

    try:
        ensure_file_overwrite_allowed(
            staging_dir,
            [
                "verification_report.md",
                "verification_report.json",
            ],
            force=args.force,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        outcome = run_verify(
            VerifyConfig(
                attack_id=attack_id,
                staging_dir=staging_dir,
            )
        )
    except ValueError as exc:
        parser.error(str(exc))

    write_text(staging_dir / "verification_report.md", outcome.verification_report_text)
    write_text(
        staging_dir / "verification_report.json",
        json.dumps(outcome.verification_report, indent=2, ensure_ascii=False) + "\n",
    )

    existing_manifest = _load_existing_manifest(staging_dir / "manifest.json")
    existing_manifest.setdefault("attack_id", attack_id)
    existing_manifest.setdefault("staging_dir", str(staging_dir))
    existing_manifest["verification_phase_e"] = {
        "verification_report_md_path": "verification_report.md",
        "verification_report_json_path": "verification_report.json",
        "verdict": outcome.verification_report.get("verdict", ""),
        "categories": outcome.verification_report.get("categories", []),
    }
    write_text(
        staging_dir / "manifest.json",
        json.dumps(existing_manifest, indent=2, ensure_ascii=False) + "\n",
    )
    print(staging_dir)


def _run_status(args: argparse.Namespace, parser: argparse.ArgumentParser) -> None:
    if not args.staging_dir and not args.attack_id:
        parser.error("status requires either --staging-dir or --attack-id")

    if args.staging_dir:
        staging_dir = Path(args.staging_dir)
        attack_id = normalize_attack_id(args.attack_id or staging_dir.name)
    else:
        attack_id = normalize_attack_id(args.attack_id)
        staging_dir = Path(args.output_dir) / attack_id

    try:
        ensure_file_overwrite_allowed(
            staging_dir,
            [
                "workflow_status.md",
                "workflow_status.json",
            ],
            force=args.force,
        )
    except ValueError as exc:
        parser.error(str(exc))

    try:
        outcome = run_workflow_status(
            WorkflowStatusConfig(
                attack_id=attack_id,
                staging_dir=staging_dir,
            )
        )
    except ValueError as exc:
        parser.error(str(exc))

    write_text(staging_dir / "workflow_status.md", outcome.workflow_status_text)
    write_text(
        staging_dir / "workflow_status.json",
        json.dumps(outcome.workflow_status, indent=2, ensure_ascii=False) + "\n",
    )

    existing_manifest = _load_existing_manifest(staging_dir / "manifest.json")
    existing_manifest.setdefault("attack_id", attack_id)
    existing_manifest.setdefault("staging_dir", str(staging_dir))
    existing_manifest["workflow_status_phase_f"] = {
        "workflow_status_md_path": "workflow_status.md",
        "workflow_status_json_path": "workflow_status.json",
        "workflow_stage": outcome.workflow_status.get("workflow_stage", ""),
        "completion_checks": outcome.workflow_status.get("completion_checks", {}),
    }
    write_text(
        staging_dir / "manifest.json",
        json.dumps(existing_manifest, indent=2, ensure_ascii=False) + "\n",
    )
    print(staging_dir)


def _fallback_attack_id(
    paper_title: str | None,
    paper_text_path: str | None,
    pdf_path: str | None,
) -> str:
    if paper_title:
        return paper_title.split(":")[0]
    if paper_text_path:
        return Path(paper_text_path).stem
    if pdf_path:
        return Path(pdf_path).stem
    return "paper_attack"


def _load_existing_manifest(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize_reference_inputs(args: argparse.Namespace) -> dict[str, object]:
    reference_repo_url = (args.reference_repo_url or "").strip()
    reference_branch = (args.reference_branch or "").strip()
    reference_root = (args.reference_root or "").strip()
    reference_paths = normalize_selected_paths(args.reference_path or [])

    if reference_repo_url and reference_root:
        raise ValueError(
            "Use either --reference-repo-url or --reference-root, not both."
        )
    if reference_branch and not reference_repo_url:
        raise ValueError("--reference-branch requires --reference-repo-url.")
    if reference_paths and not (reference_repo_url or reference_root):
        raise ValueError(
            "--reference-path requires either --reference-repo-url or --reference-root."
        )

    normalized_repo_url = normalize_repo_url(reference_repo_url) if reference_repo_url else ""
    normalized_root = ""
    if reference_root:
        root_path = Path(reference_root).expanduser().resolve()
        if not root_path.exists():
            raise ValueError(f"Reference root does not exist: {root_path}")
        if not root_path.is_dir():
            raise ValueError(f"Reference root must be a directory: {root_path}")
        normalized_root = str(root_path)

    backend_requested = ""
    if normalized_repo_url:
        backend_requested = "github_raw"
    elif normalized_root:
        backend_requested = "local_files"

    return {
        "reference_repo_url": normalized_repo_url,
        "reference_paths": reference_paths,
        "reference_branch": reference_branch,
        "reference_root": normalized_root,
        "reference_backend_requested": backend_requested,
    }


if __name__ == "__main__":
    main()
