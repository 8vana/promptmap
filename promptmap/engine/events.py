from __future__ import annotations

import sys
from dataclasses import dataclass, field

# Event type constants
EVT_INFO        = "info"
EVT_PROMPT      = "prompt"
EVT_RESPONSE    = "response"
EVT_SCORE       = "score"
EVT_BACKTRACK   = "backtrack"
EVT_ACHIEVED    = "achieved"
EVT_COMPLETE    = "complete"
EVT_ERROR       = "error"
EVT_AGENT_ACTION = "agent_action"
EVT_AGENT_DONE  = "agent_done"


@dataclass
class ProgressEvent:
    type: str
    turn: int = 0
    data: dict = field(default_factory=dict)


def fmt_cli(event: ProgressEvent) -> None:
    """Stderr fallback: print a ProgressEvent when no TUI progress queue is set.

    Goes to stderr so headless callers (e.g. ``promptmap-run``) can stream
    structured AttackResult JSONL on stdout without interleaved progress text.
    """
    from colorama import Fore, Style
    d = event.data
    t = event.turn

    def p(line: str) -> None:
        print(line, file=sys.stderr)

    if event.type == EVT_INFO:
        p(f"  {d.get('text', '')}")
    elif event.type == EVT_PROMPT:
        text = str(d.get("text", ""))[:120]
        p(f"  T{t:02d} {Fore.CYAN}[→]{Style.RESET_ALL} {text}")
    elif event.type == EVT_RESPONSE:
        text = str(d.get("text", ""))[:150]
        p(f"  T{t:02d} {Fore.YELLOW}[←]{Style.RESET_ALL} {text}")
    elif event.type == EVT_SCORE:
        score = d.get("score", 0.0)
        achieved = d.get("achieved", False)
        rationale = d.get("rationale", "")
        mark = f"{Fore.RED}✓{Style.RESET_ALL}" if achieved else "✗"
        p(f"  T{t:02d} [Score] {score:.2f} {mark} | {rationale}")
    elif event.type == EVT_BACKTRACK:
        p(f"  {Fore.YELLOW}[↩] Backtrack {d.get('count')}/{d.get('max')}{Style.RESET_ALL}")
    elif event.type == EVT_ACHIEVED:
        p(f"  {Fore.RED}[✓] Achieved at turn {d.get('turn')}{Style.RESET_ALL}")
    elif event.type == EVT_COMPLETE:
        achieved = d.get("achieved", False)
        score = d.get("score", 0.0)
        status = f"{Fore.RED}ACHIEVED{Style.RESET_ALL}" if achieved else "not achieved"
        p(f"  → {status} | final score {score:.2f}")
    elif event.type == EVT_AGENT_ACTION:
        p(f"  {Fore.CYAN}[Agent] → {d.get('attack', '')} : {d.get('objective', '')[:80]}{Style.RESET_ALL}")
    elif event.type == EVT_AGENT_DONE:
        p(f"  {Fore.GREEN}[Agent] Done: {d.get('summary', '')}{Style.RESET_ALL}")
    elif event.type == EVT_ERROR:
        p(f"  {Fore.RED}[!] {d.get('text', '')}{Style.RESET_ALL}")
