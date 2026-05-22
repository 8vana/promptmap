from __future__ import annotations

import argparse
import sys

from .profiles import list_benchmark_profiles


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="promptmap-benchmark",
        description="Run a standardized PromptMap benchmark profile and write artifacts to disk.",
    )
    parser.add_argument("--list-profiles", action="store_true",
                        help="List available benchmark profiles and exit.")
    parser.add_argument("--target-config",
                        help="YAML/JSON file describing the TargetAdapter to attack.")
    parser.add_argument("--profile",
                        help="Benchmark profile id or path.")
    parser.add_argument("--attacks", default="",
                        help="Optional comma-separated subset of attack ids to run.")
    parser.add_argument("--scorer-model", default=None,
                        help="Model name for the LLM-as-Judge scorer.")
    parser.add_argument("--scorer-provider", default=None,
                        help="Provider for scorer (openai|anthropic|gemini|bedrock|ollama). Inferred from model if omitted.")
    parser.add_argument("--adversarial-model", default=None,
                        help="Model name for the adversarial LLM. Defaults to scorer model.")
    parser.add_argument("--adversarial-provider", default=None,
                        help="Provider for adversarial LLM. Defaults to scorer provider.")
    parser.add_argument("--language", default=None,
                        help="Override the profile language.")
    parser.add_argument("--output-dir", default=None,
                        help="Output root directory for benchmark artifacts.")
    parser.add_argument("--debug", action="store_true",
                        help="Raise log level to DEBUG.")
    args = parser.parse_args()

    if args.list_profiles:
        for profile_id in list_benchmark_profiles():
            print(profile_id)
        return

    if not args.target_config:
        parser.error("--target-config is required unless --list-profiles is used.")
    if not args.profile:
        parser.error("--profile is required unless --list-profiles is used.")
    if not args.scorer_model:
        parser.error("--scorer-model is required.")

    from .runner import BenchmarkRunner, BenchmarkRunnerConfig

    attacks_override = [name.strip() for name in args.attacks.split(",") if name.strip()] or None
    config = BenchmarkRunnerConfig(
        target_config=args.target_config,
        profile=args.profile,
        scorer_model=args.scorer_model,
        scorer_provider=args.scorer_provider,
        adversarial_model=args.adversarial_model,
        adversarial_provider=args.adversarial_provider,
        output_dir=args.output_dir,
        attacks_override=attacks_override,
        language_override=args.language,
        debug=args.debug,
    )
    run_dir = BenchmarkRunner(config).run()
    sys.stdout.write(str(run_dir) + "\n")


if __name__ == "__main__":
    main()
