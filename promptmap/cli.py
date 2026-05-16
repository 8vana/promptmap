"""PromptMap CLI entry points."""

import sys


def main() -> None:
    """Launch the Textual TUI."""
    from promptmap.engine.logging_setup import setup_logging
    try:
        from promptmap.tui.app import PromptMapApp
    except ImportError as e:
        raise SystemExit(
            "TUI dependencies not installed. Run: pip install 'promptmap[tui]'"
        ) from e
    setup_logging(level="DEBUG" if "--debug" in sys.argv else None)
    PromptMapApp().run()


if __name__ == "__main__":
    main()
