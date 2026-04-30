from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import yaml


@dataclass
class NavigationStep:
    """One browser automation action in the navigation sequence."""

    action: Literal[
        "goto",
        "fill",
        "click",
        "wait_for_selector",
        "wait_for_url",
        "select",
        "press",
        "set_extra_http_headers",
        "evaluate",
    ]
    url: str | None = None        # goto
    selector: str | None = None   # fill / click / wait_for_selector / select / press
    value: str | None = None      # fill / select
    pattern: str | None = None    # wait_for_url (glob pattern)
    key: str | None = None        # press (e.g. "Enter")
    headers: dict | None = None   # set_extra_http_headers
    expression: str | None = None # evaluate (JavaScript expression)
    timeout: int = 30_000         # ms (not used by set_extra_http_headers / evaluate)


@dataclass
class ChatConfig:
    """Selectors and strategy for interacting with the embedded chat UI."""

    input_selector: str
    response_selector: str
    # None → press Enter on the input field instead of clicking a button
    send_selector: str | None = None
    response_timeout: int = 30_000
    # new_element   : wait until a new element matching response_selector appears
    # content_stable: wait until the last matching element's text stops changing
    #                 (suitable for streaming / typewriter UIs)
    response_wait_strategy: Literal["new_element", "content_stable"] = "new_element"
    # Optional button to start a fresh conversation (used by reset_conversation)
    reset_selector: str | None = None


@dataclass
class BrowserTargetConfig:
    browser: Literal["chromium", "firefox", "webkit"] = "chromium"
    headless: bool = True
    navigation: list[NavigationStep] = field(default_factory=list)
    chat: ChatConfig = field(
        default_factory=lambda: ChatConfig(input_selector="input", response_selector=".response")
    )


def load_browser_config(path: str) -> BrowserTargetConfig:
    """Load a BrowserTargetConfig from a YAML file."""
    with open(path) as f:
        data = yaml.safe_load(f)

    nav_steps = [NavigationStep(**step) for step in data.get("navigation", [])]

    chat_data = data.get("chat", {})
    chat_cfg = ChatConfig(
        input_selector=chat_data["input_selector"],
        response_selector=chat_data["response_selector"],
        send_selector=chat_data.get("send_selector"),
        response_timeout=chat_data.get("response_timeout", 30_000),
        response_wait_strategy=chat_data.get("response_wait_strategy", "new_element"),
        reset_selector=chat_data.get("reset_selector"),
    )

    return BrowserTargetConfig(
        browser=data.get("browser", "chromium"),
        headless=data.get("headless", True),
        navigation=nav_steps,
        chat=chat_cfg,
    )
