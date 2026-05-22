from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any

import yaml

from promptmap.engine.base_attack import BaseAttack

from .attack_spec import AttackSpec

_VALID_FAMILIES = {"single_turn", "multi_turn", "autonomous"}
_VALID_TARGET_MODES = {"api", "browser", "stateless", "stateful"}


class AttackRegistry:
    def __init__(self, catalog_dir: Path | None = None):
        base_dir = Path(__file__).resolve().parent.parent
        self._catalog_dir = catalog_dir or (base_dir / "catalog" / "attacks")
        self._specs_by_id: dict[str, AttackSpec] = {}
        self._specs_by_registered_name: dict[str, AttackSpec] = {}
        self._load_catalog()

    def _load_catalog(self) -> None:
        for path in sorted(self._catalog_dir.glob("*.yaml")):
            with path.open("r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            spec = AttackSpec(**data)
            self._specs_by_id[spec.attack_id] = spec
            self._specs_by_registered_name[spec.registered_name] = spec

    def list_specs(self) -> list[AttackSpec]:
        return [self._specs_by_id[k] for k in sorted(self._specs_by_id)]

    def list_attack_ids(self) -> list[str]:
        return sorted(self._specs_by_id)

    def list_registered_names(self) -> list[str]:
        return sorted(self._specs_by_registered_name)

    def get_spec(self, attack_id: str) -> AttackSpec:
        return self._specs_by_id[attack_id]

    def get_spec_by_registered_name(self, registered_name: str) -> AttackSpec:
        return self._specs_by_registered_name[registered_name]

    def load_class(self, attack_id: str) -> type[BaseAttack]:
        spec = self.get_spec(attack_id)
        module_path, attr = spec.import_path.split(":", 1)
        cls = getattr(import_module(module_path), attr)
        if not isinstance(cls, type) or not issubclass(cls, BaseAttack):
            raise TypeError(f"{spec.import_path} is not a BaseAttack subclass")
        return cls

    def create(self, attack_id: str, **kwargs: Any) -> BaseAttack:
        return self.load_class(attack_id)(**kwargs)

    def create_available_attacks(self) -> dict[str, BaseAttack]:
        attacks: dict[str, BaseAttack] = {}
        for spec in self.list_specs():
            attacks[spec.registered_name] = self.create(spec.attack_id)
        return attacks

    def validate(self) -> list[str]:
        errors: list[str] = []
        seen_ids: set[str] = set()
        seen_registered: set[str] = set()

        for path in sorted(self._catalog_dir.glob("*.yaml")):
            try:
                with path.open("r", encoding="utf-8") as f:
                    data = yaml.safe_load(f) or {}
            except Exception as exc:
                errors.append(f"{path.name}: failed to load ({exc})")
                continue

            try:
                spec = AttackSpec(**data)
            except Exception as exc:
                errors.append(f"{path.name}: invalid AttackSpec ({exc})")
                continue

            if spec.attack_id in seen_ids:
                errors.append(f"{path.name}: duplicate attack_id '{spec.attack_id}'")
            else:
                seen_ids.add(spec.attack_id)

            if spec.registered_name in seen_registered:
                errors.append(
                    f"{path.name}: duplicate registered_name '{spec.registered_name}'"
                )
            else:
                seen_registered.add(spec.registered_name)

            if spec.family not in _VALID_FAMILIES:
                errors.append(
                    f"{path.name}: unknown family '{spec.family}' "
                    f"(allowed: {sorted(_VALID_FAMILIES)})"
                )

            unknown_target_modes = sorted(set(spec.target_modes) - _VALID_TARGET_MODES)
            if unknown_target_modes:
                errors.append(
                    f"{path.name}: unknown target_modes {unknown_target_modes} "
                    f"(allowed: {sorted(_VALID_TARGET_MODES)})"
                )

            if spec.supports_benchmark and not isinstance(spec.benchmark_defaults, dict):
                errors.append(f"{path.name}: benchmark_defaults must be a mapping")

            try:
                self.load_class(spec.attack_id)
            except Exception as exc:
                errors.append(f"{path.name}: import validation failed ({exc})")

        return errors
