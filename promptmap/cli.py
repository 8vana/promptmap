"""PromptMap CLI entry points."""

from __future__ import annotations

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


# ---------------------------------------------------------------------------
# Headless run mode (promptmap-run)
# ---------------------------------------------------------------------------

# Short name → (registered attack id, importable class path).
_ATTACKS: dict[str, tuple[str, str]] = {
    "single_pi":       ("Single_PI_Attack",             "promptmap.attacks.single_pi_attack:SinglePIAttack"),
    "crescendo":       ("Multi_Crescendo_Attack",       "promptmap.attacks.multi_crescendo_attack:CrescendoAttack"),
    "pair":            ("Multi_PAIR_Attack",            "promptmap.attacks.multi_pair_attack:PAIRAttack"),
    "tap":             ("Multi_TAP_Attack",             "promptmap.attacks.multi_tap_attack:TAPAttack"),
    "chunked_request": ("Multi_Chunked_Request_Attack", "promptmap.attacks.multi_chunked_request_attack:ChunkedRequestAttack"),
    "agent":           ("AttackAgent",                  "promptmap.attacks.agent.attack_agent:AttackAgent"),
}

# class name → import path. Each entry corresponds to a TargetAdapter subclass
# that can be instantiated from a target-config file.
_ADAPTERS: dict[str, str] = {
    "OpenAITargetAdapter":    "promptmap.targets.openai_target:OpenAITargetAdapter",
    "AnthropicTargetAdapter": "promptmap.targets.anthropic_target:AnthropicTargetAdapter",
    "GeminiTargetAdapter":    "promptmap.targets.gemini_target:GeminiTargetAdapter",
    "BedrockTargetAdapter":   "promptmap.targets.bedrock_target:BedrockTargetAdapter",
    "HTTPTargetAdapter":      "promptmap.targets.http_target:HTTPTargetAdapter",
}

# OpenAI-compatible models route through factory("openai", ...); others map by prefix.
_MODEL_PROVIDER_HINTS: tuple[tuple[str, str], ...] = (
    ("gpt-",          "openai"),
    ("o1",            "openai"),
    ("o3",            "openai"),
    ("claude-",       "anthropic"),
    ("gemini-",       "gemini"),
    ("anthropic.",    "bedrock"),
    ("amazon.",       "bedrock"),
    ("meta.",         "bedrock"),
    # Bedrock cross-region inference profile IDs (e.g. us.anthropic.claude-…).
    ("us.anthropic.", "bedrock"),
    ("eu.anthropic.", "bedrock"),
    ("apac.anthropic.","bedrock"),
    ("us.amazon.",    "bedrock"),
    ("us.meta.",      "bedrock"),
)


def run() -> None:
    """Run a single attack headlessly and emit JSONL results to stdout."""
    import argparse
    import asyncio
    import json
    import os
    from datetime import datetime, timezone

    import yaml

    from promptmap.engine.context import AttackContext
    from promptmap.engine.logged_target import LoggedTargetAdapter
    from promptmap.engine.logging_setup import setup_logging
    from promptmap.memory.session_memory import SessionMemory
    from promptmap.scorers.llm_judge import LLMJudgeScorer
    from promptmap.targets.factory import create_target_adapter
    from promptmap.converters.instantiate_converters import instantiate_converters
    from promptmap.utils import load_dataset

    parser = argparse.ArgumentParser(
        prog="promptmap-run",
        description="Headless PromptMap attack runner. Emits one JSON line per AttackResult to stdout.",
    )
    parser.add_argument("--target-config", required=True,
                        help="YAML/JSON file describing the TargetAdapter to attack.")
    parser.add_argument("--attack", required=True, choices=sorted(_ATTACKS),
                        help="Attack to run.")
    parser.add_argument("--signature", required=True,
                        help="ATLAS technique ID (loaded from signatures.yaml) or a raw objective string.")
    parser.add_argument("--scorer-model", default=None,
                        help="Model name for the LLM-as-Judge scorer.")
    parser.add_argument("--scorer-provider", default=None,
                        help="Provider for scorer (openai|anthropic|gemini|bedrock|ollama). Inferred from model if omitted.")
    parser.add_argument("--adversarial-model", default=None,
                        help="Model name for the adversarial LLM (multi-turn attacks). Defaults to scorer model.")
    parser.add_argument("--adversarial-provider", default=None,
                        help="Provider for adversarial LLM. Defaults to scorer provider.")
    parser.add_argument("--converters", default="",
                        help="Comma-separated converter names to apply to the objective.")
    parser.add_argument("--language", default="en",
                        help="Language for adversarial payloads and signature lookups.")
    parser.add_argument("--debug", action="store_true",
                        help="Raise log level to DEBUG.")
    args = parser.parse_args()

    setup_logging(level="DEBUG" if args.debug else None)

    # ------------------------------------------------------------------ #
    # Load target config and build the (logged) target.
    # ------------------------------------------------------------------ #
    target_cfg = _load_target_config(args.target_config)
    raw_target = _instantiate_adapter(target_cfg)
    target_model = str(target_cfg.get("init", {}).get("model", target_cfg["adapter"]))
    target = LoggedTargetAdapter(raw_target, role="target", system=target_cfg["adapter"], model=target_model)

    # ------------------------------------------------------------------ #
    # Build scorer + adversarial LLM via the existing provider factory.
    # ------------------------------------------------------------------ #
    scorer_model = args.scorer_model or os.environ.get("PROMPTMAP_SCORE_LLM_NAME")
    if not scorer_model:
        parser.error("--scorer-model is required (or set $PROMPTMAP_SCORE_LLM_NAME).")
    scorer_provider = (
        args.scorer_provider
        or os.environ.get("PROMPTMAP_SCORE_LLM_PROVIDER")
        or _infer_provider(scorer_model)
    )
    score_llm = LoggedTargetAdapter(
        create_target_adapter(provider=scorer_provider, model=scorer_model),
        role="scorer", system=scorer_provider, model=scorer_model,
    )
    scorer = LLMJudgeScorer(judge_target=score_llm)

    adv_model = args.adversarial_model or os.environ.get("PROMPTMAP_ADV_LLM_NAME") or scorer_model
    adv_provider = (
        args.adversarial_provider
        or os.environ.get("PROMPTMAP_ADV_LLM_PROVIDER")
        or _infer_provider(adv_model)
    )
    adversarial = LoggedTargetAdapter(
        create_target_adapter(provider=adv_provider, model=adv_model),
        role="adversarial", system=adv_provider, model=adv_model,
    )

    # ------------------------------------------------------------------ #
    # Converters + attack instance.
    # ------------------------------------------------------------------ #
    converter_names = [n.strip() for n in args.converters.split(",") if n.strip()]
    converters = instantiate_converters(converter_names) if converter_names else []

    attack_id, attack_cls = _load_attack(args.attack)
    attack = attack_cls()

    ctx = AttackContext(
        target=target,
        adversarial_target=adversarial,
        scorer=scorer,
        converters=converters,
        memory=SessionMemory(),
        available_attacks={attack_id: attack},
        progress_queue=None,
        language=args.language,
    )

    # ------------------------------------------------------------------ #
    # Resolve objectives: try signatures.yaml first, else raw string.
    # ------------------------------------------------------------------ #
    try:
        entries = load_dataset("signatures.yaml", args.signature, language=args.language)
    except Exception:
        entries = []
    if entries:
        objectives = [(e["value"], e.get("prompt_technique", "")) for e in entries]
    else:
        objectives = [(args.signature, "")]

    # ------------------------------------------------------------------ #
    # Drive the attack loop and emit JSONL.
    # ------------------------------------------------------------------ #
    achieved_count = 0

    async def go() -> int:
        nonlocal achieved_count
        try:
            for objective, prompt_technique in objectives:
                kwargs = {"prompt_technique": prompt_technique} if prompt_technique else {}
                try:
                    result = await attack.run(ctx, objective, **kwargs)
                except TypeError:
                    # Attacks that do not accept prompt_technique kwarg.
                    result = await attack.run(ctx, objective)

                results = result if isinstance(result, list) else [result]
                for r in results:
                    line = _result_to_jsonl(r, args.attack, args.signature)
                    sys.stdout.write(json.dumps(line, ensure_ascii=False, default=str) + "\n")
                    sys.stdout.flush()
                    if r.achieved:
                        achieved_count += 1
        finally:
            await ctx.close_all_targets()
        return achieved_count

    achieved = asyncio.run(go())
    sys.exit(1 if achieved > 0 else 0)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_target_config(path: str) -> dict:
    import json
    import yaml

    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.lower().endswith(".json"):
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict) or "adapter" not in data:
        raise SystemExit(f"Target config {path!r} must be a mapping with an 'adapter' key.")
    return data


def _instantiate_adapter(cfg: dict):
    """Instantiate a TargetAdapter subclass from a {adapter, init} mapping."""
    import os

    class_name = cfg["adapter"]
    init = dict(cfg.get("init") or {})

    if class_name not in _ADAPTERS:
        raise SystemExit(
            f"Unknown adapter: {class_name!r}. Known: {sorted(_ADAPTERS)}."
        )
    cls = _import_object(_ADAPTERS[class_name])

    # If the adapter expects an api_key but the config omitted it, pull from env.
    if class_name == "OpenAITargetAdapter" and "api_key" not in init:
        init["api_key"] = os.getenv("OPENAI_API_KEY", "")
    if class_name == "AnthropicTargetAdapter" and "api_key" not in init:
        init["api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
    if class_name == "GeminiTargetAdapter" and "api_key" not in init:
        init["api_key"] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""

    return cls(**init)


def _load_attack(short_name: str):
    """Return (registered_id, attack_class) for a CLI short name."""
    registered_id, dotted = _ATTACKS[short_name]
    return registered_id, _import_object(dotted)


def _import_object(dotted: str):
    """Import 'pkg.mod:Name' and return Name."""
    import importlib

    module_path, attr = dotted.split(":", 1)
    return getattr(importlib.import_module(module_path), attr)


def _infer_provider(model: str) -> str:
    """Best-effort provider inference from model name."""
    for prefix, provider in _MODEL_PROVIDER_HINTS:
        if model.startswith(prefix):
            return provider
    return "openai"


def _result_to_jsonl(result, attack_short_name: str, signature_id: str) -> dict:
    """Convert an AttackResult into a stdout JSON record."""
    from datetime import datetime, timezone

    return {
        "attack":           attack_short_name,
        "signature_id":     signature_id,
        "objective":        result.objective,
        "achieved":         result.achieved,
        "score":            result.score,
        "turns":            result.turns,
        "atlas_techniques": list(result.atlas_techniques),
        "conversation": [
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in result.conversation
        ],
        "metadata":         dict(result.metadata),
        "timestamp":        datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    main()
