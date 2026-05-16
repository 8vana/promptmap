from rich.text import Text

from tui.widgets.smart_rich_log import SmartScrollRichLog


class ConversationLog(SmartScrollRichLog):
    """Scrollable conversation log with user / assistant message styling."""

    def add_user(self, text: str) -> None:
        t = Text()
        t.append("[User] → ", style="bold cyan")
        t.append(_truncate(text, 500), style="cyan")
        self.write(t)

    def add_assistant(self, text: str) -> None:
        t = Text()
        t.append("[Target] ← ", style="bold yellow")
        t.append(_truncate(text, 500), style="yellow")
        self.write(t)

    def add_info(self, text: str) -> None:
        self.write(Text(f"  {text}", style="dim white"))

    def add_separator(self, label: str = "") -> None:
        line = "─" * 50
        if label:
            line = f"── {label} " + "─" * max(0, 48 - len(label))
        self.write(Text(line, style="dim #333366"))


def _truncate(text: str, limit: int) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")
