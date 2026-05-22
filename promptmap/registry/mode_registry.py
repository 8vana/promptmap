from __future__ import annotations

from importlib import import_module
from pathlib import Path

import yaml

from .mode_spec import ModeSpec

_VALID_KINDS = {"manual", "orchestrated"}


class ModeRegistry:
    def __init__(self, catalog_dir: Path | None = None):
        base_dir = Path(__file__).resolve().parent.parent
        self._catalog_dir = catalog_dir or (base_dir / "catalog" / "modes")
        self._specs_by_id: dict[str, ModeSpec] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        for path in sorted(self._catalog_dir.glob("*.yaml")):
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            spec = ModeSpec(**data)
            self._specs_by_id[spec.mode_id] = spec

    def list_mode_ids(self) -> list[str]:
        return sorted(self._specs_by_id)

    def list_specs(self) -> list[ModeSpec]:
        return [self._specs_by_id[k] for k in sorted(self._specs_by_id)]

    def get_spec(self, mode_id: str) -> ModeSpec:
        return self._specs_by_id[mode_id]

    def load_class(self, mode_id: str):
        spec = self.get_spec(mode_id)
        if not spec.import_path:
            raise ValueError(f"Mode '{mode_id}' has no import_path")
        module_path, attr = spec.import_path.split(":", 1)
        return getattr(import_module(module_path), attr)

    def validate(self) -> list[str]:
        errors: list[str] = []
        seen_ids: set[str] = set()

        for path in sorted(self._catalog_dir.glob("*.yaml")):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception as exc:
                errors.append(f"{path.name}: failed to load ({exc})")
                continue

            try:
                spec = ModeSpec(**data)
            except Exception as exc:
                errors.append(f"{path.name}: invalid ModeSpec ({exc})")
                continue

            if spec.mode_id in seen_ids:
                errors.append(f"{path.name}: duplicate mode_id '{spec.mode_id}'")
            else:
                seen_ids.add(spec.mode_id)

            if spec.kind not in _VALID_KINDS:
                errors.append(
                    f"{path.name}: unknown kind '{spec.kind}' "
                    f"(allowed: {sorted(_VALID_KINDS)})"
                )

            if spec.import_path:
                try:
                    self.load_class(spec.mode_id)
                except Exception as exc:
                    errors.append(f"{path.name}: import validation failed ({exc})")

        return errors
