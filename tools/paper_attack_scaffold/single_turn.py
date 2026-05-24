from __future__ import annotations

from typing import Any


SUPPORTED_SINGLE_TURN_SKELETONS = (
    "single_turn_template",
    "single_turn_splice",
    "dataset_rank_then_attack",
)


def is_single_turn_family(family: str) -> bool:
    return str(family).strip() == "single_turn"


def is_supported_single_turn_skeleton(execution_skeleton: str) -> bool:
    return str(execution_skeleton).strip() in SUPPORTED_SINGLE_TURN_SKELETONS


def infer_single_turn_profile_name(execution_skeleton: str) -> str:
    if is_supported_single_turn_skeleton(execution_skeleton):
        return "single_turn"
    return "generic"


def has_complete_step_symbol_map(
    algorithm_steps: list[dict[str, Any]],
    step_symbol_map: dict[str, Any],
) -> bool:
    expected_ids = [
        str(step.get("step_id") or "").strip()
        for step in algorithm_steps
        if isinstance(step, dict) and str(step.get("step_id") or "").strip()
    ]
    if not expected_ids:
        return False
    if not isinstance(step_symbol_map, dict):
        return False
    for step_id in expected_ids:
        mapping = step_symbol_map.get(step_id)
        if not isinstance(mapping, dict):
            return False
        target_symbol = str(mapping.get("target_symbol") or "").strip()
        if not target_symbol:
            return False
    return True
