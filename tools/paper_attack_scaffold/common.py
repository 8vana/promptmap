from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

VALID_FAMILIES = {"single_turn", "multi_turn", "autonomous"}
VALID_TARGET_MODES = {"api", "browser", "stateless", "stateful"}


def render_template(name: str, context: dict[str, Any]) -> str:
    path = Path(__file__).resolve().parent / "templates" / name
    text = path.read_text(encoding="utf-8")

    def replace(match: re.Match[str]) -> str:
        key = match.group(1).strip()
        if key not in context:
            raise KeyError(f"Unknown template key: {key}")
        return str(context[key])

    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", replace, text)


def normalize_attack_id(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    normalized = re.sub(r"[^a-z0-9_]", "", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    if not normalized:
        raise ValueError("attack_id must contain at least one alphanumeric character")
    return normalized


def to_class_name(attack_id: str) -> str:
    return "".join(part.capitalize() for part in attack_id.split("_")) + "Attack"


def to_registered_name(attack_id: str, family: str) -> str:
    prefix = {
        "single_turn": "Single",
        "multi_turn": "Multi",
        "autonomous": "Autonomous",
    }[family]
    body = "_".join(part.capitalize() for part in attack_id.split("_"))
    return f"{prefix}_{body}_Attack"


def parse_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_params(entries: list[str]) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for entry in entries:
        if "=" not in entry:
            raise ValueError(f"Parameter must use KEY=VALUE syntax: {entry!r}")
        key, raw_value = entry.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Parameter key cannot be empty: {entry!r}")
        parsed[key] = yaml.safe_load(raw_value)
    return parsed


def yaml_inline(values: list[str]) -> str:
    return _yaml_clean_dump(values, flow_style=True)


def yaml_inline_or_mapping(value: dict[str, Any]) -> str:
    return _yaml_clean_dump(value, flow_style=True)


def yaml_scalar(value: Any) -> str:
    return _yaml_clean_dump(value, flow_style=True)


def _yaml_clean_dump(value: Any, flow_style: bool) -> str:
    dumped = yaml.safe_dump(value, default_flow_style=flow_style, sort_keys=False)
    lines = [line for line in dumped.splitlines() if line.strip() != "..."]
    return "\n".join(lines).strip()


def bullet_block(values: list[str]) -> str:
    if not values:
        return "- none specified"
    return "\n  ".join(f"- `{value}`" for value in values)


def write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def ensure_file_overwrite_allowed(
    target_dir: Path,
    filenames: list[str],
    *,
    force: bool,
) -> None:
    if force:
        target_dir.mkdir(parents=True, exist_ok=True)
        return
    conflicts = [name for name in filenames if (target_dir / name).exists()]
    if conflicts:
        raise ValueError(
            f"Refusing to overwrite existing files in {target_dir}: {conflicts}. "
            "Use --force to overwrite."
        )
    target_dir.mkdir(parents=True, exist_ok=True)
