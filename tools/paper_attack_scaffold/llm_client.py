from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from promptmap.targets.factory import create_target_adapter, get_missing_env_vars


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    model: str


async def run_prompt(config: LLMConfig, system_prompt: str, user_prompt: str) -> str:
    target = create_target_adapter(provider=config.provider, model=config.model)
    conversation_id = "paper-attack-planner"
    try:
        target.set_system_prompt(system_prompt, conversation_id)
        return await target.send(user_prompt, conversation_id)
    finally:
        target.reset_conversation(conversation_id)
        await target.close()


def run_prompt_sync(config: LLMConfig, system_prompt: str, user_prompt: str) -> str:
    missing = get_missing_env_vars(config.provider)
    if missing:
        raise RuntimeError(
            f"Missing environment for provider '{config.provider}': {missing}"
        )
    return asyncio.run(run_prompt(config, system_prompt, user_prompt))


def parse_json_response(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1])
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
                return parsed if isinstance(parsed, dict) else {}
            except json.JSONDecodeError:
                pass
    return {}
