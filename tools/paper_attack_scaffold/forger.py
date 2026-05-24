from __future__ import annotations

from dataclasses import dataclass
import json
import pprint
from pathlib import Path
import py_compile
import re
from typing import Any

from .common import (
    bullet_block,
    normalize_attack_id,
    render_template,
    to_class_name,
    to_registered_name,
    yaml_inline,
    yaml_inline_or_mapping,
    yaml_scalar,
)
from .llm_client import LLMConfig, parse_json_response, run_prompt_sync
from .single_turn import infer_single_turn_profile_name


@dataclass(frozen=True)
class ForgeConfig:
    attack_id: str
    staging_dir: Path
    source_type: str = "generated"
    provider: str | None = None
    model: str | None = None
    forge_backend: str = "heuristic"


@dataclass(frozen=True)
class ForgeOutcome:
    attack_id: str
    display_name: str
    family: str
    module_name: str
    class_name: str
    registered_name: str
    execution_skeleton: str
    classification_signals: list[str]
    workflow_profile: str
    attack_module_text: str
    attack_catalog_text: str
    benchmark_notes_text: str
    review_checklist_text: str
    generation_notes_text: str
    py_compile_ok: bool
    forge_backend_used: str
    raw_payload: dict[str, Any] | None = None
    raw_response_text: str = ""


def build_forge_artifacts(config: ForgeConfig) -> ForgeOutcome:
    plan_path = config.staging_dir / "implementation_plan.json"
    if not plan_path.exists():
        raise ValueError(f"Missing implementation plan: {plan_path}")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    _validate_plan(plan, plan_path)
    if config.forge_backend == "llm" and (not config.provider or not config.model):
        raise ValueError("--forge-backend llm requires both provider and model.")

    attack_id = normalize_attack_id(plan.get("attack_id") or config.attack_id)
    display_name = str(plan.get("display_name") or _display_name_from_attack_id(attack_id))
    family = str(plan.get("family") or "single_turn")
    module_name = f"{attack_id}_attack"
    class_name = to_class_name(attack_id)
    registered_name = to_registered_name(attack_id, family)

    description = _build_description(plan)
    target_modes = _clean_list(plan.get("target_modes")) or ["api"]
    required_capabilities = _clean_list(plan.get("required_capabilities")) or ["scorer_llm"]
    planner_default_params = (
        plan.get("default_params") if isinstance(plan.get("default_params"), dict) else {}
    )
    repo_derived_hints = _derive_repo_hint_params(plan)
    default_params = dict(planner_default_params)
    for key, value in repo_derived_hints.items():
        default_params.setdefault(key, value)
    benchmark_defaults: dict[str, Any] = {}
    tags = _derive_tags(plan)
    compatible_atlas_techniques: list[str] = []
    execution_skeleton, classification_signals = _classify_execution_skeleton(plan)
    workflow_profile = infer_single_turn_profile_name(execution_skeleton) if family == "single_turn" else family
    step_symbol_map = _build_step_symbol_map(plan, execution_skeleton)
    selected_instruction_default = _infer_selected_instruction_default(default_params)
    affirmation_examples, rejection_examples = _split_prompt_fragments(plan.get("prompt_fragments"))

    context = {
        "attack_id": attack_id,
        "attack_id_yaml": yaml_scalar(attack_id),
        "display_name": display_name,
        "display_name_yaml": yaml_scalar(display_name),
        "family": family,
        "family_yaml": yaml_scalar(family),
        "description": description,
        "description_yaml": yaml_scalar(description),
        "paper_title": str(plan.get("paper_title") or ""),
        "paper_title_yaml": yaml_scalar(str(plan.get("paper_title") or "")),
        "paper_url": str(plan.get("paper_url") or ""),
        "paper_url_yaml": yaml_scalar(str(plan.get("paper_url") or "")),
        "paper_year_yaml": yaml_scalar(None),
        "paper_title_or_tbd": str(plan.get("paper_title") or "TBD"),
        "paper_url_or_tbd": str(plan.get("paper_url") or "TBD"),
        "paper_title_repr": repr(str(plan.get("paper_title") or "")),
        "paper_url_repr": repr(str(plan.get("paper_url") or "")),
        "source_type": config.source_type,
        "source_type_yaml": yaml_scalar(config.source_type),
        "prompt_technique_aware": yaml_scalar(False),
        "prompt_technique_aware_display": "false",
        "supports_benchmark": yaml_scalar(False),
        "supports_benchmark_display": "false",
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
        "registered_name_repr": repr(registered_name),
        "family_repr": repr(family),
        "execution_skeleton": execution_skeleton,
        "execution_skeleton_repr": repr(execution_skeleton),
        "classification_signals_literal": _py_literal(classification_signals),
        "workflow_profile": workflow_profile,
        "workflow_profile_repr": repr(workflow_profile),
        "summary_literal": _py_literal(str(plan.get("summary") or "")),
        "default_params_literal": _py_literal(default_params),
        "repo_derived_hints_literal": _py_literal(repo_derived_hints),
        "plan_steps_literal": _py_literal(plan.get("algorithm_steps") or []),
        "prompt_fragments_literal": _py_literal(plan.get("prompt_fragments") or []),
        "ambiguities_literal": _py_literal(plan.get("ambiguities") or []),
        "default_params_repr": _py_literal(default_params),
        "selected_instruction_default_literal": _py_literal(selected_instruction_default),
        "affirmation_examples_literal": _py_literal(affirmation_examples),
        "rejection_examples_literal": _py_literal(rejection_examples),
        "step_symbol_map_literal": _py_literal(step_symbol_map),
        "plan_step_ids_literal": _py_literal(
            [step.get("step_id") for step in plan.get("algorithm_steps", []) if isinstance(step, dict)]
        ),
    }

    attack_module_text = render_template(_template_for_execution_skeleton(execution_skeleton), context)
    attack_catalog_text = render_template("attack_catalog.yaml.j2", context)
    benchmark_notes_text = render_template("benchmark_notes.md.j2", context)
    review_checklist_text = render_template("review_checklist.md.j2", context)
    generation_notes_text = _render_generation_notes(
        plan=plan,
        execution_skeleton=execution_skeleton,
        step_symbol_map=step_symbol_map,
        repo_derived_hints=repo_derived_hints,
        classification_signals=classification_signals,
        workflow_profile=workflow_profile,
    )
    forge_backend_used = "heuristic"
    raw_payload: dict[str, Any] | None = None
    raw_response_text = ""

    want_llm = (
        config.forge_backend in {"auto", "llm"}
        and config.provider
        and config.model
    )
    if want_llm:
        try:
            llm_result = _run_llm_forge(
                llm_config=LLMConfig(provider=config.provider, model=config.model),
                plan=plan,
                execution_skeleton=execution_skeleton,
                class_name=class_name,
                registered_name=registered_name,
                heuristic_attack_module_text=attack_module_text,
                heuristic_generation_notes_text=generation_notes_text,
            )
            candidate_module_text = str(llm_result.get("attack_module_text") or "").strip()
            candidate_generation_notes_text = str(llm_result.get("generation_notes_text") or "").strip()
            if candidate_module_text:
                attack_module_text = candidate_module_text + ("\n" if not candidate_module_text.endswith("\n") else "")
            if candidate_generation_notes_text:
                generation_notes_text = candidate_generation_notes_text + (
                    "\n" if not candidate_generation_notes_text.endswith("\n") else ""
                )
            raw_payload = llm_result
            raw_response_text = llm_result.get("_raw_response_text", "")
            forge_backend_used = "llm"
        except Exception as exc:
            if config.forge_backend == "llm":
                raise
            generation_notes_text = _append_generation_note(
                generation_notes_text,
                f"LLM forge fallback triggered after error: {type(exc).__name__}: {exc}",
            )

    py_compile_ok = _check_compiles(config.staging_dir / "_forge_tmp_attack_module.py", attack_module_text)
    if not py_compile_ok and forge_backend_used == "llm" and config.forge_backend == "auto":
        attack_module_text = render_template(_template_for_execution_skeleton(execution_skeleton), context)
        generation_notes_text = _append_generation_note(
            generation_notes_text,
            "LLM forge output failed py_compile; fell back to heuristic attack module.",
        )
        py_compile_ok = _check_compiles(config.staging_dir / "_forge_tmp_attack_module.py", attack_module_text)
        forge_backend_used = "heuristic"

    return ForgeOutcome(
        attack_id=attack_id,
        display_name=display_name,
        family=family,
        module_name=module_name,
        class_name=class_name,
        registered_name=registered_name,
        execution_skeleton=execution_skeleton,
        classification_signals=classification_signals,
        workflow_profile=workflow_profile,
        attack_module_text=attack_module_text,
        attack_catalog_text=attack_catalog_text,
        benchmark_notes_text=benchmark_notes_text,
        review_checklist_text=review_checklist_text,
        generation_notes_text=generation_notes_text,
        py_compile_ok=py_compile_ok,
        forge_backend_used=forge_backend_used,
        raw_payload=raw_payload,
        raw_response_text=raw_response_text,
    )


def _validate_plan(plan: dict[str, Any], plan_path: Path) -> None:
    required = ["attack_id", "display_name", "paper_title", "family", "algorithm_steps"]
    missing = [key for key in required if key not in plan]
    if missing:
        raise ValueError(f"Plan at {plan_path} is missing required keys: {missing}")


def _clean_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    return [str(item).strip() for item in raw if str(item).strip()]


def _derive_tags(plan: dict[str, Any]) -> list[str]:
    tags = ["generated", "research", "paper_forge"]
    family = str(plan.get("family") or "").strip()
    if family:
        tags.append(family)
    summary = str(plan.get("summary") or "").lower()
    if "jailbreak" in summary:
        tags.append("jailbreak")
    if "prompt" in summary:
        tags.append("prompt_injection")
    return list(dict.fromkeys(tags))


def _build_description(plan: dict[str, Any]) -> str:
    summary = str(plan.get("summary") or "").strip()
    if summary:
        return summary
    return f"Plan-driven draft for the research attack '{plan.get('display_name') or plan.get('attack_id')}'."


def _display_name_from_attack_id(attack_id: str) -> str:
    return " ".join(
        part.upper() if len(part) <= 3 else part.capitalize()
        for part in attack_id.split("_")
    ) + " Attack"


def _py_literal(value: Any) -> str:
    return pprint.pformat(value, width=88, sort_dicts=False)


def _check_compiles(temp_path: Path, source: str) -> bool:
    temp_path.write_text(source, encoding="utf-8")
    try:
        py_compile.compile(str(temp_path), doraise=True)
        return True
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _classify_execution_skeleton(plan: dict[str, Any]) -> tuple[str, list[str]]:
    family = str(plan.get("family") or "").strip()
    steps = plan.get("algorithm_steps") or []
    step_text = " ".join(
        f"{step.get('step_id', '')} {step.get('title', '')} {step.get('description', '')}"
        for step in steps
        if isinstance(step, dict)
    ).lower()
    prompt_text = " ".join(
        fragment.get("text", "")
        for fragment in (plan.get("prompt_fragments") or [])
        if isinstance(fragment, dict)
    ).lower()

    signals: list[str] = []

    if family == "autonomous":
        return "autonomous_loop", ["family=autonomous"]
    if family == "multi_turn":
        return "multi_turn_refinement", ["family=multi_turn"]

    has_rank = any(token in step_text for token in ("rank", "score"))
    has_select = "select" in step_text
    has_splice = "splice" in step_text or "prefix" in step_text or "suffix" in step_text
    has_collect = any(token in step_text for token in ("collect", "dataset", "candidate"))
    if has_rank:
        signals.append("has_rank_or_score_steps")
    if has_select:
        signals.append("has_select_step")
    if has_splice:
        signals.append("has_splice_or_prefix_suffix_step")
    if has_collect:
        signals.append("has_collect_or_dataset_step")
    if prompt_text:
        signals.append("has_prompt_fragments")

    if has_rank and has_select and has_splice and has_collect:
        return "dataset_rank_then_attack", signals
    if has_splice:
        return "single_turn_splice", signals
    if prompt_text:
        return "single_turn_template", signals
    signals.append("defaulted_to_single_turn_template")
    return "single_turn_template", signals


def _template_for_execution_skeleton(execution_skeleton: str) -> str:
    if execution_skeleton == "dataset_rank_then_attack":
        return "attack_module_dataset_rank_then_attack.py.j2"
    if execution_skeleton == "single_turn_splice":
        return "attack_module_single_turn_splice.py.j2"
    if execution_skeleton == "multi_turn_refinement":
        return "attack_module_multi_turn_refinement.py.j2"
    if execution_skeleton == "autonomous_loop":
        return "attack_module_autonomous_loop.py.j2"
    return "attack_module_forge.py.j2"


def _build_step_symbol_map(plan: dict[str, Any], execution_skeleton: str) -> dict[str, dict[str, Any]]:
    mapping: dict[str, dict[str, Any]] = {}
    for step in plan.get("algorithm_steps", []):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "").strip()
        if not step_id:
            continue
        symbol = _step_symbol_for(step_id, execution_skeleton)
        todo_only = _todo_only_for_step(step_id, execution_skeleton)
        mapping[step_id] = {
            "mapping_type": "helper_method" if symbol.startswith("_") else "metadata_only",
            "target_symbol": symbol,
            "todo_only": todo_only,
        }
    return mapping


def _step_symbol_for(step_id: str, execution_skeleton: str) -> str:
    if execution_skeleton == "dataset_rank_then_attack":
        explicit = {
            "construct_responses": "_build_response_templates",
            "collect_instructions": "_collect_candidate_instructions",
            "calculate_probabilities": "_calculate_response_tendencies",
            "calculate_response_tendencies": "_calculate_response_tendencies",
            "score_instructions": "_rank_candidate_instructions",
            "rank_instructions": "_rank_candidate_instructions",
            "filter_instructions": "_filter_text_manipulation_instructions",
            "select_top_instructions": "_select_top_instructions",
            "splice_instructions": "_build_attack_prompt",
        }
        if step_id in explicit:
            return explicit[step_id]
    if execution_skeleton == "single_turn_splice":
        explicit = {
            "construct_responses": "_build_prompt_segments",
            "filter_instructions": "_build_prompt_segments",
            "splice_instructions": "_build_attack_prompt",
        }
        if step_id in explicit:
            return explicit[step_id]
    if execution_skeleton == "multi_turn_refinement":
        explicit = {
            "build_initial_prompt": "_build_initial_prompt",
            "construct_initial_framing": "_build_initial_prompt",
            "construct_responses": "_build_initial_prompt",
            "query_target_iteratively": "_run_refinement_loop",
            "refine_based_on_target_feedback": "_refine_prompt",
            "analyze_response": "_analyze_response",
        }
        if step_id in explicit:
            return explicit[step_id]
    if execution_skeleton == "autonomous_loop":
        explicit = {
            "select_attack_primitive": "_select_action",
            "execute_and_adapt": "_execute_action",
            "evaluate_completion": "_score_progress",
        }
        if step_id in explicit:
            return explicit[step_id]
    return f"step::{step_id}"


def _todo_only_for_step(step_id: str, execution_skeleton: str) -> bool:
    if execution_skeleton == "dataset_rank_then_attack":
        return step_id in {
            "construct_responses",
            "collect_instructions",
            "calculate_probabilities",
            "calculate_response_tendencies",
        }
    if execution_skeleton == "single_turn_splice":
        return step_id not in {"splice_instructions"}
    if execution_skeleton == "multi_turn_refinement":
        return True
    if execution_skeleton == "autonomous_loop":
        return True
    return True


def _infer_selected_instruction_default(default_params: dict[str, Any]) -> int:
    count = default_params.get("spliced_instructions_count")
    if isinstance(count, list) and count:
        for item in count:
            if isinstance(item, int):
                return item
    if isinstance(count, int):
        return count
    return 2


def _split_prompt_fragments(raw_fragments: Any) -> tuple[list[str], list[str]]:
    affirmations: list[str] = []
    rejections: list[str] = []
    if not isinstance(raw_fragments, list):
        return affirmations, rejections
    for fragment in raw_fragments:
        if not isinstance(fragment, dict):
            continue
        name = str(fragment.get("name") or "").lower()
        text = str(fragment.get("text") or "").strip()
        if not text:
            continue
        if "affirmation" in name:
            affirmations.append(text)
        elif "rejection" in name:
            rejections.append(text)
    return affirmations, rejections


def _derive_repo_hint_params(plan: dict[str, Any]) -> dict[str, Any]:
    hints: dict[str, Any] = {}
    for divergence in plan.get("divergences", []):
        if not isinstance(divergence, dict):
            continue
        if str(divergence.get("paper_position") or "").strip().lower() != "not specified":
            continue
        topic = str(divergence.get("topic") or "").strip()
        repo_position = str(divergence.get("repo_position") or "").strip()
        if not topic or not repo_position:
            continue
        value = _parse_repo_position_value(topic, repo_position)
        if value is None:
            continue
        hints[topic] = value
    return hints


def _parse_repo_position_value(topic: str, repo_position: str) -> Any | None:
    match = re.search(
        rf"\b{re.escape(topic)}\b\s*=\s*([\"']?[-a-zA-Z0-9_.]+[\"']?)",
        repo_position,
    )
    if not match:
        return None
    raw_value = match.group(1).strip()
    if raw_value.startswith(("'", '"')) and raw_value.endswith(("'", '"')):
        return raw_value[1:-1]
    if raw_value.isdigit():
        return int(raw_value)
    try:
        return float(raw_value)
    except ValueError:
        return raw_value


def _render_generation_notes(
    *,
    plan: dict[str, Any],
    execution_skeleton: str,
    step_symbol_map: dict[str, dict[str, Any]],
    repo_derived_hints: dict[str, Any],
    classification_signals: list[str],
    workflow_profile: str,
) -> str:
    lines: list[str] = []
    lines.append(f"# Generation Notes: {plan.get('display_name') or plan.get('attack_id')}")
    lines.append("")
    lines.append("## Skeleton")
    lines.append("")
    lines.append(f"- `execution_skeleton`: `{execution_skeleton}`")
    lines.append(f"- `family`: `{plan.get('family')}`")
    lines.append(f"- `workflow_profile`: `{workflow_profile}`")
    lines.append("")
    lines.append("## Classification Signals")
    lines.append("")
    for signal in classification_signals or ["none"]:
        lines.append(f"- `{signal}`")
    lines.append("")
    lines.append("## Step Mapping")
    lines.append("")
    for step in plan.get("algorithm_steps", []):
        if not isinstance(step, dict):
            continue
        step_id = str(step.get("step_id") or "")
        mapping = step_symbol_map.get(step_id, {})
        todo_only = mapping.get("todo_only")
        suffix = " (todo-only)" if todo_only else ""
        lines.append(f"- `{step_id}` -> `{mapping.get('target_symbol', 'unmapped')}`{suffix}")
    lines.append("")
    lines.append("## Preserved Ambiguities")
    lines.append("")
    for ambiguity in plan.get("ambiguities", []) or ["none"]:
        lines.append(f"- {ambiguity}")
    lines.append("")
    lines.append("## Repo Support")
    lines.append("")
    repo_evidence = plan.get("repo_evidence") or []
    if repo_evidence:
        lines.append(f"- `repo_evidence_count`: `{len(repo_evidence)}`")
        for record in repo_evidence:
            if not isinstance(record, dict):
                continue
            path = str(record.get("path") or "unknown")
            evidence_id = str(record.get("evidence_id") or "unknown")
            lines.append(f"- `{evidence_id}` from `{path}`")
    else:
        lines.append("- No repo evidence recorded.")
    lines.append("")
    lines.append("## Repo-Derived Hints")
    lines.append("")
    if repo_derived_hints:
        for key, value in repo_derived_hints.items():
            lines.append(f"- `{key}` = `{value}`")
    else:
        lines.append("- No repo-derived defaults were promoted into `DEFAULT_PARAMS`.")
    lines.append("")
    lines.append("## Divergences")
    lines.append("")
    divergences = plan.get("divergences") or []
    if divergences:
        for divergence in divergences:
            if not isinstance(divergence, dict):
                continue
            lines.append(
                f"- `{divergence.get('topic', 'unknown')}`: "
                f"paper={divergence.get('paper_position', 'unknown')} | "
                f"repo={divergence.get('repo_position', 'unknown')}"
            )
            lines.append(f"  decision: {divergence.get('planner_decision', 'unknown')}")
    else:
        lines.append("- No divergences recorded.")
    lines.append("")
    return "\n".join(lines)


def _append_generation_note(generation_notes_text: str, note: str) -> str:
    text = generation_notes_text.rstrip()
    if not text:
        return note + "\n"
    return text + "\n\n## Forge Backend Notes\n\n- " + note + "\n"


def _run_llm_forge(
    *,
    llm_config: LLMConfig,
    plan: dict[str, Any],
    execution_skeleton: str,
    class_name: str,
    registered_name: str,
    heuristic_attack_module_text: str,
    heuristic_generation_notes_text: str,
) -> dict[str, Any]:
    prompts_dir = Path(__file__).resolve().parent / "prompts"
    system_prompt = (prompts_dir / "forge_system.txt").read_text(encoding="utf-8")
    user_template = (prompts_dir / "forge_user.txt").read_text(encoding="utf-8")
    user_prompt = user_template.format(
        attack_id=str(plan.get("attack_id") or ""),
        display_name=str(plan.get("display_name") or ""),
        paper_title=str(plan.get("paper_title") or ""),
        paper_url=str(plan.get("paper_url") or ""),
        execution_skeleton=execution_skeleton,
        class_name=class_name,
        registered_name=registered_name,
        implementation_plan_json=json.dumps(plan, indent=2, ensure_ascii=False),
        heuristic_attack_module_text=heuristic_attack_module_text,
        heuristic_generation_notes_text=heuristic_generation_notes_text,
    )
    raw = run_prompt_sync(llm_config, system_prompt=system_prompt, user_prompt=user_prompt)
    payload = parse_json_response(raw)
    if not payload:
        raise RuntimeError("LLM forge returned an empty or non-JSON response.")
    payload["_raw_response_text"] = raw
    if not isinstance(payload.get("attack_module_text"), str):
        raise RuntimeError("LLM forge response is missing 'attack_module_text'.")
    if not isinstance(payload.get("generation_notes_text"), str):
        raise RuntimeError("LLM forge response is missing 'generation_notes_text'.")
    return payload
