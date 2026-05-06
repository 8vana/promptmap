"""Modal file picker for selecting a YAML file path.

Used by the Settings screen to make Browser Config Path entry less error-prone.
The user clicks "Browse..." next to the input → this modal opens with a
filesystem tree → on selection the picked absolute path is returned and the
input field is updated.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Button, DirectoryTree, Input, Label


class _YamlFilteredTree(DirectoryTree):
    """DirectoryTree that hides files which are clearly not YAML.

    Directories and .yaml / .yml files are shown. Other files are hidden so
    the user has less visual noise to scan through.
    """

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        for p in paths:
            try:
                if p.is_dir():
                    # ドット始まりの隠しディレクトリ（.git 等）は除外
                    if p.name.startswith("."):
                        continue
                    yield p
                elif p.suffix.lower() in (".yaml", ".yml"):
                    yield p
            except OSError:
                # アクセス不可なパスは黙ってスキップ
                continue


class FilePickerScreen(ModalScreen[str | None]):
    """Modal screen that lets the user pick a YAML file from the filesystem.

    Dismisses with the selected absolute path string, or None if cancelled.
    """

    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, start_path: str = "") -> None:
        super().__init__()
        # 初期表示ディレクトリ: 引数のパスがディレクトリならそこ、ファイルなら親、
        # 空または存在しなければカレントディレクトリ。
        self._initial_dir = self._resolve_initial_dir(start_path)

    @staticmethod
    def _resolve_initial_dir(start_path: str) -> str:
        if start_path:
            p = Path(start_path).expanduser()
            if p.is_dir():
                return str(p)
            if p.exists() and p.parent.is_dir():
                return str(p.parent)
        return os.getcwd()

    def compose(self) -> ComposeResult:
        with Container(id="file-picker-dialog"):
            yield Label("Select a YAML file", classes="panel-title")
            yield Label(
                "Use ↑↓ to navigate, Enter to expand a directory or pick a file. Esc to cancel.",
                classes="field-label",
            )
            yield Input(
                value=self._initial_dir,
                id="file-picker-path",
                placeholder="/absolute/path/to/file.yaml",
            )
            yield _YamlFilteredTree(self._initial_dir, id="file-picker-tree")
            with Horizontal(id="file-picker-buttons"):
                yield Button("Use this path", id="btn-use",    variant="primary")
                yield Button("Cancel",        id="btn-cancel")

    def on_directory_tree_file_selected(
        self, event: DirectoryTree.FileSelected
    ) -> None:
        # ツリー上のファイル選択 → Input にパスを反映（ボタン押下時に確定）
        self.query_one("#file-picker-path", Input).value = str(event.path)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-use":
            path = self.query_one("#file-picker-path", Input).value.strip()
            self.dismiss(path or None)
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)
