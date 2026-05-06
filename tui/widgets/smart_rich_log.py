"""``RichLog`` subclass that respects user scroll position.

Textual's stock ``RichLog(auto_scroll=True)`` calls ``self.scroll_end(...)``
unconditionally on every write, even when the user has scrolled up to read
back through history. The view snaps back to the bottom on the next line —
which makes it impossible to read past activity in a fast-flowing log.

``SmartScrollRichLog`` overrides ``write()`` to pass ``scroll_end`` based on
the *current* scroll position before the write:

  * View at the bottom → keep auto-scrolling (default behaviour).
  * User has scrolled up → don't yank the view; new lines accumulate
    silently below. Scrolling back to the bottom resumes auto-scroll.
"""

from __future__ import annotations

from textual.widgets import RichLog


class SmartScrollRichLog(RichLog):
    """RichLog that pauses auto-scroll while the user is scrolled up."""

    def write(self, content, *args, **kwargs):
        # Only override scroll_end if the caller didn't pass it (kwargs or
        # positional — it's the 4th positional after content/width/expand/shrink).
        if "scroll_end" not in kwargs and len(args) < 4:
            kwargs["scroll_end"] = self.is_vertical_scroll_end
        return super().write(content, *args, **kwargs)
