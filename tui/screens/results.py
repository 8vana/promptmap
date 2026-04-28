from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import Button, DataTable, Footer, Header, Label, RichLog
from textual.containers import Container, Horizontal

from engine.models import AttackResult
from tui.widgets.result_table import ResultTable


class ResultsScreen(Screen):
    BINDINGS = [Binding("escape", "go_back", "Back")]

    def compose(self) -> ComposeResult:
        yield Header()
        yield Label("Results", classes="panel-title")
        with Horizontal(id="results-body"):
            with Container(id="result-table-container"):
                yield ResultTable(id="results-table")
            with Container(id="detail-container"):
                yield Label("Detail", classes="panel-title")
                yield RichLog(id="detail-log")
        with Horizontal(id="results-footer-row"):
            yield Button("Export JSON", id="btn-export", variant="primary")
            yield Button("Back",        id="btn-back")
            yield Label("", id="export-label")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#results-table", ResultTable)
        for r in self.app.session_memory.get_results():
            table.add_result(r)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        results = self.app.session_memory.get_results()
        if 0 <= event.cursor_row < len(results):
            self._show_detail(results[event.cursor_row])

    def _show_detail(self, result: AttackResult) -> None:
        log = self.query_one("#detail-log", RichLog)
        log.clear()
        log.write(Text(f"Attack:    {result.attack_name}", style="bold"))
        log.write(Text(f"Objective: {result.objective}", style="dim"))
        log.write(Text(f"Score: {result.score:.2f}  Turns: {result.turns}", style="bold"))
        achieved_label = "✓ Achieved" if result.achieved else "✗ Not achieved"
        log.write(Text(achieved_label, style="bold red" if result.achieved else "bold"))
        log.write(Text("─" * 40, style="dim"))
        for msg in result.conversation:
            if msg.role == "user":
                t = Text()
                t.append("[User] → ", style="bold cyan")
                t.append(msg.content[:300], style="cyan")
                log.write(t)
            elif msg.role == "assistant":
                t = Text()
                t.append("[Target] ← ", style="bold yellow")
                t.append(msg.content[:300], style="yellow")
                log.write(t)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-export":
            self._export_json()
        elif event.button.id == "btn-back":
            self.app.pop_screen()

    def _export_json(self) -> None:
        results = self.app.session_memory.get_results()
        if not results:
            self.notify("No results to export.", severity="warning")
            return
        out_path = "promptmap_results.json"
        self.app.session_memory.export_json(out_path)
        self.query_one("#export-label", Label).update(f"Saved → {out_path}")
        self.notify(f"Exported {len(results)} results.", title="Export", severity="information")

    def action_go_back(self) -> None:
        self.app.pop_screen()
