from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header, Label, Button, Static
from textual.containers import Container, Horizontal, Vertical

_LOGO = (
    "██████╗ ██████╗  ██████╗ ███╗   ███╗██████╗ ████████╗███╗   ███╗ █████╗ ██████╗\n"
    "██╔══██╗██╔══██╗██╔═══██╗████╗ ████║██╔══██╗╚══██╔══╝████╗ ████║██╔══██╗██╔══██╗\n"
    "██████╔╝██████╔╝██║   ██║██╔████╔██║██████╔╝   ██║   ██╔████╔██║███████║██████╔╝\n"
    "██╔═══╝ ██╔══██╗██║   ██║██║╚██╔╝██║██╔═══╝    ██║   ██║╚██╔╝██║██╔══██║██╔═══╝\n"
    "██║     ██║  ██║╚██████╔╝██║ ╚═╝ ██║██║        ██║   ██║ ╚═╝ ██║██║  ██║██║\n"
    "╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝     ╚═╝╚═╝        ╚═╝   ╚═╝     ╚═╝╚═╝  ╚═╝╚═╝"
)


class HomeScreen(Screen):
    BINDINGS = [
        Binding("m", "go_manual",   "Manual",   show=True),
        Binding("a", "go_agent",    "Agent",    show=True),
        Binding("s", "go_settings", "Settings", show=True),
        Binding("r", "go_results",  "Results",  show=True),
        Binding("l", "go_logs",     "Logs",     show=True),
        Binding("q", "quit",        "Quit",     show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)

        yield Static(_LOGO, id="logo")

        with Container(id="status-panel"):
            yield Label("", id="lbl-target")
            yield Label("", id="lbl-adv")
            yield Label("", id="lbl-score")
            yield Label("", id="lbl-apikey")

        with Horizontal(id="nav-row"):
            yield Button("Manual Scan [M]",  id="btn-manual",   classes="nav-btn")
            yield Button("Agent Scan  [A]",  id="btn-agent",    classes="nav-btn")
            yield Button("Settings    [S]",  id="btn-settings", classes="nav-btn")
            yield Button("Results     [R]",  id="btn-results",  classes="nav-btn")
            yield Button("Logs        [L]",  id="btn-logs",     classes="nav-btn")

        with Container(id="recent-box"):
            yield Label("Recent Results", classes="panel-title")
            yield DataTable(id="recent-table")

        yield Footer()

    def on_mount(self) -> None:
        self._refresh_status()
        self._refresh_results()
        from proverb import get_random_proverb
        self.notify(get_random_proverb(), title="Proverb", timeout=10)

    def _refresh_status(self) -> None:
        s = self.app.settings
        ready = "● Ready" if self.app.settings_ready() else "○ Not configured"
        if s.get("target_type") == "browser":
            target_display = f"[Browser] {s.get('browser_config_path', '(not set)')}"
        else:
            target_display = s.get("api_endpoint", "(not set)")
        self.query_one("#lbl-target", Label).update(f"Target   : {target_display}")
        self.query_one("#lbl-adv",    Label).update(
            f"Adv LLM  : {s.get('adv_llm_name', '(not set)')}"
        )
        self.query_one("#lbl-score",  Label).update(
            f"Score LLM: {s.get('score_llm_name', '(not set)')}"
        )
        self.query_one("#lbl-apikey", Label).update(f"Status   : {ready}")

    def _refresh_results(self) -> None:
        table = self.query_one("#recent-table", DataTable)
        table.clear(columns=True)
        table.add_columns("Attack", "Objective", "Score", "Result")
        for r in self.app.session_memory.get_results()[-10:]:
            status = "✓" if r.achieved else "✗"
            table.add_row(
                r.attack_name,
                r.objective[:40] + ("…" if len(r.objective) > 40 else ""),
                f"{r.score:.2f}",
                status,
            )

    # ── navigation ──────────────────────────────────────────────────────

    def on_button_pressed(self, event: Button.Pressed) -> None:
        mapping = {
            "btn-manual":   self.action_go_manual,
            "btn-agent":    self.action_go_agent,
            "btn-settings": self.action_go_settings,
            "btn-results":  self.action_go_results,
            "btn-logs":     self.action_go_logs,
        }
        action = mapping.get(event.button.id)
        if action:
            action()

    def action_go_manual(self) -> None:
        from tui.screens.manual_scan import ManualScanScreen
        self.app.push_screen(ManualScanScreen())

    def action_go_agent(self) -> None:
        from tui.screens.agent_scan import AgentScanScreen
        self.app.push_screen(AgentScanScreen())

    def action_go_settings(self) -> None:
        from tui.screens.settings import SettingsScreen
        self.app.push_screen(SettingsScreen())

    def action_go_results(self) -> None:
        from tui.screens.results import ResultsScreen
        self.app.push_screen(ResultsScreen())

    def action_go_logs(self) -> None:
        from tui.screens.log_viewer import LogViewerScreen
        self.app.push_screen(LogViewerScreen())

    def on_screen_resume(self) -> None:
        self._refresh_status()
        self._refresh_results()
