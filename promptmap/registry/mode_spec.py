from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModeSpec:
    mode_id: str
    display_name: str
    description: str
    kind: str
    import_path: str = ""
    supports_tui: bool = True
    supports_cli: bool = True
    supports_benchmark: bool = False
