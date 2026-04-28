import json
from dataclasses import asdict

from engine.models import AttackResult


class SessionMemory:
    """Lightweight in-process memory for one scan session."""

    def __init__(self):
        self._results: list[AttackResult] = []

    def save_result(self, result: AttackResult) -> None:
        self._results.append(result)

    def get_results(self) -> list[AttackResult]:
        return list(self._results)

    def summary(self) -> dict:
        total = len(self._results)
        achieved = sum(1 for r in self._results if r.achieved)
        return {
            "total": total,
            "achieved": achieved,
            "rate": achieved / total if total else 0.0,
        }

    def export_json(self, path: str) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump([asdict(r) for r in self._results], f, indent=2, ensure_ascii=False)
        print(f"Results exported to {path}")
