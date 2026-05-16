from __future__ import annotations

import os

from engine.base_target import TargetAdapter

# ---------------------------------------------------------------------------
# Provider metadata
# ---------------------------------------------------------------------------

PROVIDER_LABELS: dict[str, str] = {
    "openai":    "OpenAI",
    "anthropic": "Anthropic",
    "gemini":    "Google Gemini",
    "bedrock":   "Amazon Bedrock",
    "ollama":    "Ollama (local)",
}

# Required env vars per provider.
# For "gemini", either GEMINI_API_KEY or GOOGLE_API_KEY is sufficient (OR logic).
_PROVIDER_REQUIRED_ENV: dict[str, list[str]] = {
    "openai":    ["OPENAI_API_KEY"],
    "anthropic": ["ANTHROPIC_API_KEY"],
    "gemini":    ["GEMINI_API_KEY", "GOOGLE_API_KEY"],
    "bedrock":   ["AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY"],
    "ollama":    [],
}


def is_provider_available(provider: str) -> bool:
    """Return True if all required env vars for the provider are set."""
    required = _PROVIDER_REQUIRED_ENV.get(provider, [])
    if not required:
        return True
    if provider == "gemini":
        return any(os.getenv(v) for v in required)
    return all(bool(os.getenv(v)) for v in required)


def get_available_providers() -> dict[str, bool]:
    """Return availability status for every known provider."""
    return {p: is_provider_available(p) for p in _PROVIDER_REQUIRED_ENV}


def get_missing_env_vars(provider: str) -> list[str]:
    """Return the list of env var names that are missing for the given provider."""
    required = _PROVIDER_REQUIRED_ENV.get(provider, [])
    if provider == "gemini":
        if not any(os.getenv(v) for v in required):
            return required  # show both so the user knows either works
        return []
    return [v for v in required if not os.getenv(v)]


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_target_adapter(provider: str, model: str) -> TargetAdapter:
    """Instantiate the appropriate TargetAdapter for the given provider."""
    if provider == "openai":
        from targets.openai_target import OpenAITargetAdapter
        return OpenAITargetAdapter(
            model=model,
            api_key=os.getenv("OPENAI_API_KEY", ""),
        )

    if provider == "ollama":
        from targets.openai_target import OpenAITargetAdapter
        return OpenAITargetAdapter(
            model=model,
            api_key="ollama",
            endpoint=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1"),
        )

    if provider == "anthropic":
        from targets.anthropic_target import AnthropicTargetAdapter
        return AnthropicTargetAdapter(
            model=model,
            api_key=os.getenv("ANTHROPIC_API_KEY", ""),
        )

    if provider == "gemini":
        from targets.gemini_target import GeminiTargetAdapter
        return GeminiTargetAdapter(model=model)

    if provider == "bedrock":
        from targets.bedrock_target import BedrockTargetAdapter
        return BedrockTargetAdapter(
            model=model,
            region=os.getenv("AWS_REGION", "us-east-1"),
        )

    raise ValueError(f"Unknown provider: '{provider}'")
