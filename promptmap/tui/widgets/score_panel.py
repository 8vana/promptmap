from rich.text import Text

from tui.widgets.smart_rich_log import SmartScrollRichLog

_BAR_WIDTH = 10


class ScorePanel(SmartScrollRichLog):
    """Turn-by-turn score history displayed as mini progress bars."""

    def add_score(
        self,
        turn: int,
        score: float,
        achieved: bool,
        rationale: str = "",
    ) -> None:
        filled = round(score * _BAR_WIDTH)
        bar = "█" * filled + "░" * (_BAR_WIDTH - filled)

        t = Text()
        t.append(f"T{turn:02d} ", style="dim")
        t.append(f"[{bar}] ", style="red" if achieved else "blue")
        t.append(f"{score:.2f} ", style="bold")
        t.append("✓" if achieved else "✗", style="bold red" if achieved else "dim green")
        if rationale:
            t.append(f"\n     {rationale[:55]}", style="dim italic")
        self.write(t)
