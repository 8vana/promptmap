from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

import yaml

from promptmap.registry import get_attack_registry

from .models import BenchmarkObjective, BenchmarkProfile

_DATASET_DIR = Path(__file__).resolve().parent.parent / "datasets"
_PROFILE_DIR = _DATASET_DIR / "benchmark_profiles"
_BASE_LANGUAGE = "en"


def list_benchmark_profiles() -> list[str]:
    return sorted(path.stem for path in _PROFILE_DIR.glob("*.yaml"))


def load_benchmark_profile(profile_ref: str) -> BenchmarkProfile:
    path = _resolve_profile_path(profile_ref)
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return BenchmarkProfile(**data)


def resolve_benchmark_objectives(
    profile: BenchmarkProfile,
    language_override: str | None = None,
) -> list[BenchmarkObjective]:
    language = language_override or profile.language
    entries = _load_signature_entries(profile.dataset_source, language=language)
    resolver = profile.objective_resolver or {}
    mode = resolver.get("mode")
    if mode == "frozen_list":
        return _resolve_frozen_list(profile.profile_id, entries, resolver)
    if mode == "rules":
        return _resolve_rules(profile.profile_id, entries, resolver)
    raise ValueError(f"Unknown benchmark objective_resolver mode: {mode!r}")


def validate_benchmark_profiles() -> list[str]:
    errors: list[str] = []
    attack_registry = get_attack_registry()
    for path in sorted(_PROFILE_DIR.glob("*.yaml")):
        try:
            profile = load_benchmark_profile(str(path))
        except Exception as exc:
            errors.append(f"{path.name}: failed to load ({exc})")
            continue

        for attack_id in profile.attack_ids:
            try:
                spec = attack_registry.get_spec(attack_id)
            except KeyError:
                errors.append(f"{path.name}: unknown attack_id '{attack_id}'")
                continue
            if not spec.supports_benchmark:
                errors.append(
                    f"{path.name}: attack '{attack_id}' is not benchmarkable"
                )

        try:
            resolve_benchmark_objectives(profile)
        except Exception as exc:
            errors.append(f"{path.name}: objective resolution failed ({exc})")

    return errors


def _resolve_profile_path(profile_ref: str) -> Path:
    candidate = Path(profile_ref)
    if candidate.exists():
        return candidate
    if candidate.suffix != ".yaml":
        candidate = _PROFILE_DIR / f"{profile_ref}.yaml"
    else:
        candidate = _PROFILE_DIR / candidate.name
    if not candidate.exists():
        raise FileNotFoundError(f"Benchmark profile not found: {profile_ref}")
    return candidate


def _load_signature_entries(dataset_source: str, language: str) -> list[dict[str, Any]]:
    path = _DATASET_DIR / dataset_source
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    entries: list[dict[str, Any]] = []
    ordinals: defaultdict[tuple[str, str], int] = defaultdict(int)

    for group in data.get("signatures", []) or []:
        atlas_id = group.get("atlas_technique", "")
        prompt_techniques = group.get("prompt_techniques", {}) or {}
        for prompt_technique, technique_body in prompt_techniques.items():
            prompts = technique_body.get("prompts", []) if isinstance(technique_body, dict) else []
            for prompt_entry in prompts:
                if not isinstance(prompt_entry, dict):
                    continue
                value, used = _resolve_language(prompt_entry, language)
                if not value:
                    continue
                key = (atlas_id, prompt_technique)
                ordinal = ordinals[key]
                ordinals[key] += 1
                entries.append(
                    {
                        "objective": value,
                        "atlas_technique": atlas_id,
                        "prompt_technique": prompt_technique,
                        "language_used": used,
                        "is_fallback": used != language,
                        "ordinal": ordinal,
                    }
                )
    return entries


def _resolve_language(prompt_entry: dict[str, Any], language: str) -> tuple[str, str]:
    if language in prompt_entry and isinstance(prompt_entry[language], str) and prompt_entry[language]:
        return prompt_entry[language], language
    if _BASE_LANGUAGE in prompt_entry and isinstance(prompt_entry[_BASE_LANGUAGE], str) and prompt_entry[_BASE_LANGUAGE]:
        return prompt_entry[_BASE_LANGUAGE], _BASE_LANGUAGE
    for key, value in prompt_entry.items():
        if isinstance(value, str) and value:
            return value, key
    return "", ""


def _resolve_frozen_list(
    profile_id: str,
    entries: list[dict[str, Any]],
    resolver: dict[str, Any],
) -> list[BenchmarkObjective]:
    resolved: list[BenchmarkObjective] = []
    for idx, ref in enumerate(resolver.get("signature_refs", []) or []):
        atlas_id = ref.get("atlas_technique", "")
        prompt_technique = ref.get("prompt_technique")
        ordinal = int(ref.get("ordinal", 0))
        matches = [
            entry for entry in entries
            if entry["atlas_technique"] == atlas_id
            and (prompt_technique is None or entry["prompt_technique"] == prompt_technique)
        ]
        if ordinal >= len(matches):
            raise ValueError(
                f"frozen_list ref #{idx + 1} could not resolve "
                f"(atlas_technique={atlas_id!r}, prompt_technique={prompt_technique!r}, ordinal={ordinal})"
            )
        entry = matches[ordinal]
        objective_id = ref.get(
            "objective_id",
            f"{entry['atlas_technique']}:{entry['prompt_technique']}:{entry['ordinal']}",
        )
        resolved.append(
            BenchmarkObjective(
                objective_id=objective_id,
                objective=entry["objective"],
                atlas_technique=entry["atlas_technique"],
                prompt_technique=entry["prompt_technique"],
                language_used=entry["language_used"],
                is_fallback=entry["is_fallback"],
                ordinal=entry["ordinal"],
            )
        )
    return resolved


def _resolve_rules(
    profile_id: str,
    entries: list[dict[str, Any]],
    resolver: dict[str, Any],
) -> list[BenchmarkObjective]:
    include_atlas = set(resolver.get("include_atlas_techniques", []) or [])
    include_prompt_techniques = set(resolver.get("include_prompt_techniques", []) or [])
    per_atlas_limit = int(
        resolver.get("per_atlas_technique_limit", resolver.get("per_atlas_limit", 1))
    )
    max_objectives = int(resolver.get("max_objectives", 0))

    counts: defaultdict[str, int] = defaultdict(int)
    resolved: list[BenchmarkObjective] = []

    for entry in entries:
        if include_atlas and entry["atlas_technique"] not in include_atlas:
            continue
        if include_prompt_techniques and entry["prompt_technique"] not in include_prompt_techniques:
            continue
        if counts[entry["atlas_technique"]] >= per_atlas_limit:
            continue

        objective_id = (
            f"{entry['atlas_technique']}:{entry['prompt_technique']}:{entry['ordinal']}"
        )
        resolved.append(
            BenchmarkObjective(
                objective_id=objective_id,
                objective=entry["objective"],
                atlas_technique=entry["atlas_technique"],
                prompt_technique=entry["prompt_technique"],
                language_used=entry["language_used"],
                is_fallback=entry["is_fallback"],
                ordinal=entry["ordinal"],
            )
        )
        counts[entry["atlas_technique"]] += 1
        if max_objectives and len(resolved) >= max_objectives:
            break

    if not resolved:
        raise ValueError(f"rules resolver for profile '{profile_id}' produced no objectives")
    return resolved
