from __future__ import annotations

from dataclasses import dataclass
import json
import pprint
from pathlib import Path
import py_compile
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


@dataclass(frozen=True)
class ForgeConfig:
    attack_id: str
    staging_dir: Path
    source_type: str = "generated"


@dataclass(frozen=True)
class ForgeOutcome:
    attack_id: str
    display_name: str
    family: str
    module_name: str
    class_name: str
    registered_name: str
    attack_module_text: str
    attack_catalog_text: str
    benchmark_notes_text: str
    review_checklist_text: str
    py_compile_ok: bool


def build_forge_artifacts(config: ForgeConfig) -> ForgeOutcome:
    plan_path = config.staging_dir / "implementation_plan.json"
    if not plan_path.exists():
        raise ValueError(f"Missing implementation plan: {plan_path}")

    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    _validate_plan(plan, plan_path)

    attack_id = normalize_attack_id(plan.get("attack_id") or config.attack_id)
    display_name = str(plan.get("display_name") or _display_name_from_attack_id(attack_id))
    family = str(plan.get("family") or "single_turn")
    module_name = f"{attack_id}_attack"
    class_name = to_class_name(attack_id)
    registered_name = to_registered_name(attack_id, family)

    description = _build_description(plan)
    target_modes = _clean_list(plan.get("target_modes")) or ["api"]
    required_capabilities = _clean_list(plan.get("required_capabilities")) or ["scorer_llm"]
    default_params = plan.get("default_params") if isinstance(plan.get("default_params"), dict) else {}
    benchmark_defaults: dict[str, Any] = {}
    tags = _derive_tags(plan)
    compatible_atlas_techniques: list[str] = []

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
        "summary_literal": _py_literal(str(plan.get("summary") or "")),
        "default_params_literal": _py_literal(default_params),
        "plan_steps_literal": _py_literal(plan.get("algorithm_steps") or []),
        "prompt_fragments_literal": _py_literal(plan.get("prompt_fragments") or []),
        "ambiguities_literal": _py_literal(plan.get("ambiguities") or []),
        "default_params_repr": _py_literal(default_params),
        "plan_step_ids_literal": _py_literal(
            [step.get("step_id") for step in plan.get("algorithm_steps", []) if isinstance(step, dict)]
        ),
    }

    attack_module_text = render_template("attack_module_forge.py.j2", context)
    attack_catalog_text = render_template("attack_catalog.yaml.j2", context)
    benchmark_notes_text = render_template("benchmark_notes.md.j2", context)
    review_checklist_text = render_template("review_checklist.md.j2", context)

    py_compile_ok = _check_compiles(config.staging_dir / "_forge_tmp_attack_module.py", attack_module_text)

    return ForgeOutcome(
        attack_id=attack_id,
        display_name=display_name,
        family=family,
        module_name=module_name,
        class_name=class_name,
        registered_name=registered_name,
        attack_module_text=attack_module_text,
        attack_catalog_text=attack_catalog_text,
        benchmark_notes_text=benchmark_notes_text,
        review_checklist_text=review_checklist_text,
        py_compile_ok=py_compile_ok,
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
