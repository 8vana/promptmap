from textual.widgets import DataTable

from engine.models import AttackResult


class ResultTable(DataTable):
    """DataTable pre-configured for AttackResult rows."""

    def on_mount(self) -> None:
        self.add_columns("Attack", "Objective", "Score", "Result", "Turns")
        self.cursor_type = "row"

    def add_result(self, result: AttackResult) -> None:
        status = "✓ Achieved" if result.achieved else "✗ Not achieved"
        obj = result.objective[:48] + ("…" if len(result.objective) > 48 else "")
        self.add_row(
            result.attack_name,
            obj,
            f"{result.score:.2f}",
            status,
            str(result.turns),
        )

    def populate(self, results: list[AttackResult]) -> None:
        self.clear()
        for r in results:
            self.add_result(r)
