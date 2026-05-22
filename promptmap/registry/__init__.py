from __future__ import annotations

from functools import lru_cache

from .attack_registry import AttackRegistry
from .attack_spec import AttackSpec
from .mode_registry import ModeRegistry
from .mode_spec import ModeSpec


@lru_cache(maxsize=1)
def get_attack_registry() -> AttackRegistry:
    return AttackRegistry()


@lru_cache(maxsize=1)
def get_mode_registry() -> ModeRegistry:
    return ModeRegistry()


__all__ = [
    "AttackRegistry",
    "AttackSpec",
    "ModeRegistry",
    "ModeSpec",
    "get_attack_registry",
    "get_mode_registry",
]
