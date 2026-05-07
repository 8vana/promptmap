"""PromptMap entry point.

Launches the Textual TUI. ``--debug`` raises the log level to DEBUG; the
``$PROMPTMAP_LOG_LEVEL`` env var is honoured otherwise (default INFO).
"""

import sys

from engine.logging_setup import setup_logging
from tui.app import PromptMapApp


def main() -> None:
    setup_logging(level="DEBUG" if "--debug" in sys.argv else None)
    PromptMapApp().run()


if __name__ == "__main__":
    main()
