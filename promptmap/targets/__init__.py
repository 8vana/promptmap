from .factory import (
    PROVIDER_LABELS,
    create_target_adapter,
    get_available_providers,
    get_missing_env_vars,
)
from .http_target import HTTPTargetAdapter
from .openai_target import OpenAITargetAdapter
from .playwright_target import PlaywrightTargetAdapter

try:
    from .anthropic_target import AnthropicTargetAdapter
except (ModuleNotFoundError, ImportError):
    AnthropicTargetAdapter = None

try:
    from .gemini_target import GeminiTargetAdapter
except (ModuleNotFoundError, ImportError):
    GeminiTargetAdapter = None

try:
    from .bedrock_target import BedrockTargetAdapter
except (ModuleNotFoundError, ImportError):
    BedrockTargetAdapter = None
