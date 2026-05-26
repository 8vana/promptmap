from __future__ import annotations

import re

PLACEHOLDER_MARKERS = {
    "todo_marker": ("todo(", "todo:"),
    "draft_status": ('"forge_status": "draft"', "'forge_status': 'draft'"),
    "draft_runtime_banner": ("forge draft executing",),
    "placeholder_score": ("placeholder_score",),
    "placeholder_rationale": ("placeholder_rationale",),
    "draft_review_note": ("validate the attack flow against the paper",),
}


def find_placeholder_markers(source: str) -> list[str]:
    lowered = source.lower()
    found: list[str] = []
    for name, markers in PLACEHOLDER_MARKERS.items():
        if any(marker in lowered for marker in markers):
            found.append(name)
    return found


def has_placeholder_markers(source: str) -> bool:
    return bool(find_placeholder_markers(source))


def extract_forge_status(source: str) -> str:
    match = re.search(r"['\"]forge_status['\"]\s*:\s*['\"]([a-z_]+)['\"]", source)
    if not match:
        return ""
    return match.group(1).strip().lower()


def replace_forge_status(source: str, new_status: str) -> str:
    updated, count = re.subn(
        r"((['\"])forge_status\2\s*:\s*(['\"]))([a-z_]+)(\3)",
        rf"\1{new_status}\5",
        source,
        count=1,
    )
    return updated if count else source
