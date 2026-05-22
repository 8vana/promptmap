from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from promptmap.engine.context import AttackContext
from promptmap.engine.logged_target import LoggedTargetAdapter
from promptmap.engine.logging_setup import setup_logging
from promptmap.memory.session_memory import SessionMemory
from promptmap.registry import get_attack_registry
from promptmap.scorers.llm_judge import LLMJudgeScorer
from promptmap.targets.factory import create_target_adapter

from .profiles import load_benchmark_profile, resolve_benchmark_objectives
from .reporters import create_run_directory, write_aggregate_outputs, write_manifest, write_raw_results

_SCORER_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "scorers" / "prompts"


@dataclass(frozen=True)
class BenchmarkRunnerConfig:
    target_config: str
    profile: str
    scorer_model: str
    scorer_provider: str | None = None
    adversarial_model: str | None = None
    adversarial_provider: str | None = None
    output_dir: str | None = None
    attacks_override: list[str] | None = None
    language_override: str | None = None
    debug: bool = False


class BenchmarkRunner:
    def __init__(self, config: BenchmarkRunnerConfig):
        self.config = config
        self.attack_registry = get_attack_registry()

    def run(self) -> Path:
        setup_logging(level="DEBUG" if self.config.debug else None)
        return asyncio.run(self.run_async())

    async def run_async(self) -> Path:
        profile = load_benchmark_profile(self.config.profile)
        objectives = resolve_benchmark_objectives(
            profile,
            language_override=self.config.language_override,
        )
        attack_ids = self.config.attacks_override or profile.attack_ids
        attack_specs = [self.attack_registry.get_spec(attack_id) for attack_id in attack_ids]

        target_cfg = _load_target_config(self.config.target_config)
        raw_target = _instantiate_adapter(target_cfg)
        target_model = str(target_cfg.get("init", {}).get("model", target_cfg["adapter"]))
        target = LoggedTargetAdapter(
            raw_target,
            role="target",
            system=target_cfg["adapter"],
            model=target_model,
        )

        scorer_provider = (
            self.config.scorer_provider
            or os.environ.get("PROMPTMAP_SCORE_LLM_PROVIDER")
            or _infer_provider(self.config.scorer_model)
        )
        score_llm = LoggedTargetAdapter(
            create_target_adapter(provider=scorer_provider, model=self.config.scorer_model),
            role="scorer",
            system=scorer_provider,
            model=self.config.scorer_model,
        )
        scorer_prompt = _load_scorer_prompt(profile.scorer_policy.get("prompt_profile", "benchmark_v1"))
        scorer = LLMJudgeScorer(
            judge_target=score_llm,
            threshold=float(profile.scorer_policy.get("threshold", 0.7)),
            prompt_template=scorer_prompt,
        )

        adv_model = (
            self.config.adversarial_model
            or os.environ.get("PROMPTMAP_ADV_LLM_NAME")
            or self.config.scorer_model
        )
        adv_provider = (
            self.config.adversarial_provider
            or os.environ.get("PROMPTMAP_ADV_LLM_PROVIDER")
            or _infer_provider(adv_model)
        )
        adversarial = LoggedTargetAdapter(
            create_target_adapter(provider=adv_provider, model=adv_model),
            role="adversarial",
            system=adv_provider,
            model=adv_model,
        )

        ctx = AttackContext(
            target=target,
            adversarial_target=adversarial,
            scorer=scorer,
            converters=[],
            memory=SessionMemory(),
            available_attacks=self.attack_registry.create_available_attacks(),
            progress_queue=_NullProgressQueue(),
            language=self.config.language_override or profile.language,
        )

        run_dir = create_run_directory(self.config.output_dir)
        started_at = datetime.now(timezone.utc).isoformat()
        raw_rows: list[dict[str, Any]] = []

        try:
            for spec in attack_specs:
                attack = self.attack_registry.create(spec.attack_id)
                attack_kwargs = dict(spec.benchmark_defaults or {})
                attack_kwargs.update((profile.attack_overrides or {}).get(spec.attack_id, {}))
                for objective in objectives:
                    try:
                        if spec.prompt_technique_aware:
                            result = await attack.run(
                                ctx,
                                objective.objective,
                                prompt_technique=objective.prompt_technique,
                                **attack_kwargs,
                            )
                        else:
                            result = await attack.run(ctx, objective.objective, **attack_kwargs)
                    except TypeError:
                        result = await attack.run(ctx, objective.objective, **attack_kwargs)
                    ctx.memory.save_result(result)
                    raw_rows.append(
                        {
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "profile_id": profile.profile_id,
                            "profile_version": profile.version,
                            "target_label": f"{target_cfg['adapter']}:{target_model}",
                            "attack_id": spec.attack_id,
                            "registered_name": spec.registered_name,
                            "display_name": spec.display_name,
                            "objective_id": objective.objective_id,
                            "atlas_technique": objective.atlas_technique,
                            "prompt_technique": objective.prompt_technique,
                            "objective": objective.objective,
                            "achieved": result.achieved,
                            "score": result.score,
                            "turns": result.turns,
                            "metadata": dict(result.metadata),
                        }
                    )
        finally:
            await ctx.close_all_targets()

        finished_at = datetime.now(timezone.utc).isoformat()
        manifest = {
            "started_at": started_at,
            "finished_at": finished_at,
            "profile": {
                "profile_id": profile.profile_id,
                "version": profile.version,
                "dataset_source": profile.dataset_source,
                "language": self.config.language_override or profile.language,
                "tags": list(profile.tags),
            },
            "target": _redact_target_config(target_cfg),
            "attack_ids": attack_ids,
            "objective_count": len(objectives),
            "run_count": len(raw_rows),
            "scorer_model": self.config.scorer_model,
            "scorer_provider": scorer_provider,
            "adversarial_model": adv_model,
            "adversarial_provider": adv_provider,
        }
        write_manifest(run_dir, manifest)
        write_raw_results(run_dir, raw_rows)
        write_aggregate_outputs(run_dir, raw_rows)
        return run_dir


class _NullProgressQueue:
    async def put(self, event) -> None:
        return None


def _load_scorer_prompt(prompt_profile: str) -> str:
    path = _SCORER_PROMPTS_DIR / f"{prompt_profile}.txt"
    with path.open("r", encoding="utf-8") as f:
        return f.read()


def _load_target_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    if path.lower().endswith(".json"):
        data = json.loads(text)
    else:
        data = yaml.safe_load(text)
    if not isinstance(data, dict) or "adapter" not in data:
        raise ValueError(f"Target config {path!r} must be a mapping with an 'adapter' key.")
    return data


def _instantiate_adapter(cfg: dict):
    class_name = cfg["adapter"]
    init = dict(cfg.get("init") or {})

    from promptmap.cli import _ADAPTERS, _import_object

    if class_name not in _ADAPTERS:
        raise ValueError(f"Unknown adapter: {class_name!r}. Known: {sorted(_ADAPTERS)}.")
    cls = _import_object(_ADAPTERS[class_name])

    if class_name == "OpenAITargetAdapter" and "api_key" not in init:
        init["api_key"] = os.getenv("OPENAI_API_KEY", "")
    if class_name == "AnthropicTargetAdapter" and "api_key" not in init:
        init["api_key"] = os.getenv("ANTHROPIC_API_KEY", "")
    if class_name == "GeminiTargetAdapter" and "api_key" not in init:
        init["api_key"] = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or ""

    return cls(**init)


def _infer_provider(model: str) -> str:
    from promptmap.cli import _MODEL_PROVIDER_HINTS

    for prefix, provider in _MODEL_PROVIDER_HINTS:
        if model.startswith(prefix):
            return provider
    return "openai"


def _redact_target_config(cfg: dict[str, Any]) -> dict[str, Any]:
    redacted = json.loads(json.dumps(cfg))
    init = redacted.get("init")
    if isinstance(init, dict):
        for key in list(init.keys()):
            if "key" in key.lower() or "token" in key.lower():
                init[key] = "***"
    return redacted
