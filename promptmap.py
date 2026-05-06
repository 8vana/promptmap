import os
import cmd
import json
import asyncio
import inquirer
from colorama import init, Fore, Style
init(autoreset=True)

from ascii_art import image_to_colored_ascii_with_promptmap
from proverb import show_random_proverb
from utils import (
    load_atlas_catalog, load_dataset, select_prompts,
    select_converters, select_jailbreak_methods, select_response_converter,
    apply_jailbreak_method, apply_response_converter_method, print_result,
)
from converters.instantiate_converters import instantiate_converters

from engine.context import AttackContext
from memory.session_memory import SessionMemory
from targets.http_target import HTTPTargetAdapter
from targets.factory import (
    create_target_adapter, get_available_providers,
    get_missing_env_vars, PROVIDER_LABELS,
)
from scorers.llm_judge import LLMJudgeScorer

from attacks.single_pi_attack import SinglePIAttack
from attacks.multi_crescendo_attack import CrescendoAttack
from attacks.multi_pair_attack import PAIRAttack
from attacks.multi_tap_attack import TAPAttack
from attacks.multi_chunked_request_attack import ChunkedRequestAttack
from attacks.agent.attack_agent import AttackAgent


class PromptMapInteractiveShell(cmd.Cmd):
    intro = f"{Fore.GREEN}Welcome to the 'promptmap' interactive shell! Type help or ? to list commands.{Style.RESET_ALL}\n"
    prompt = f"{Fore.BLUE}(promptmap) {Style.RESET_ALL}"

    config_file = os.path.expanduser("~/.promptmap_config.json")

    settings = {
        "target_type":       "http",
        "api_endpoint":      "",
        "body_template":     '{"text": "{PROMPT}"}',
        "response_key":      "text",
        "browser_config_path": "",
        "adv_llm_provider":  "openai",
        "adv_llm_name":      "",
        "score_llm_provider": "openai",
        "score_llm_name":    "",
    }

    def __init__(self):
        super().__init__()
        self.load_settings()

    # Map of setting key -> environment variable name.
    # When set, env vars override values loaded from the JSON config file.
    _ENV_OVERRIDES = {
        "adv_llm_provider":   "PROMPTMAP_ADV_LLM_PROVIDER",
        "adv_llm_name":       "PROMPTMAP_ADV_LLM_NAME",
        "score_llm_provider": "PROMPTMAP_SCORE_LLM_PROVIDER",
        "score_llm_name":     "PROMPTMAP_SCORE_LLM_NAME",
    }

    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    self.settings.update(json.load(f))
                print("Settings loaded from file.")
            except Exception as e:
                print(f"Failed to load settings: {e}")

        for key, env_name in self._ENV_OVERRIDES.items():
            value = (os.getenv(env_name) or "").strip()
            if value:
                self.settings[key] = value
                print(f"Settings: '{key}' overridden by ${env_name}")

        availability = get_available_providers()
        adv_provider = self.settings.get("adv_llm_provider", "openai")
        score_provider = self.settings.get("score_llm_provider", "openai")

        for role, provider in [("Adversarial LLM", adv_provider), ("Score LLM", score_provider)]:
            if not availability.get(provider, False):
                missing = get_missing_env_vars(provider)
                print(f"[!] {role} provider '{PROVIDER_LABELS.get(provider, provider)}' "
                      f"requires env var(s): {', '.join(missing)}")

    def save_settings(self):
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.settings, f, indent=2)
            print("Settings saved.")
        except Exception as e:
            print(f"Failed to save settings: {e}")

    # ------------------------------------------------------------------
    # Context builder (shared by manual and agent)
    # ------------------------------------------------------------------
    def _build_context(self, converter_instances=None) -> AttackContext:
        from engine.logged_target import LoggedTargetAdapter
        s = self.settings

        if s.get("target_type") == "browser":
            from targets.browser_config import load_browser_config
            from targets.playwright_target import PlaywrightTargetAdapter
            cfg = load_browser_config(s["browser_config_path"])
            raw_target = PlaywrightTargetAdapter(cfg)
            target_system, target_model = "browser_target", s.get("browser_config_path", "")
        else:
            raw_target = HTTPTargetAdapter(
                endpoint=s["api_endpoint"],
                body_template=json.loads(s["body_template"]),
                response_key=s["response_key"],
            )
            target_system, target_model = "http_target", s.get("api_endpoint", "")

        objective_target = LoggedTargetAdapter(
            raw_target, role="target", system=target_system, model=target_model,
        )
        adversarial_target = LoggedTargetAdapter(
            create_target_adapter(provider=s["adv_llm_provider"], model=s["adv_llm_name"]),
            role="adversarial", system=s["adv_llm_provider"], model=s["adv_llm_name"],
        )
        score_llm = LoggedTargetAdapter(
            create_target_adapter(provider=s["score_llm_provider"], model=s["score_llm_name"]),
            role="scorer", system=s["score_llm_provider"], model=s["score_llm_name"],
        )
        scorer = LLMJudgeScorer(judge_target=score_llm)
        memory = SessionMemory()

        available_attacks = {
            "Single_PI_Attack":             SinglePIAttack(),
            "Multi_Crescendo_Attack":       CrescendoAttack(),
            "Multi_PAIR_Attack":            PAIRAttack(),
            "Multi_TAP_Attack":             TAPAttack(),
            "Multi_Chunked_Request_Attack": ChunkedRequestAttack(),
        }

        return AttackContext(
            target=objective_target,
            adversarial_target=adversarial_target,
            scorer=scorer,
            converters=converter_instances or [],
            memory=memory,
            available_attacks=available_attacks,
        )

    def _validate_settings(self) -> bool:
        s = self.settings
        availability = get_available_providers()

        missing: list[str] = []

        for role, provider_key, name_key in [
            ("Adversarial LLM", "adv_llm_provider", "adv_llm_name"),
            ("Score LLM",       "score_llm_provider", "score_llm_name"),
        ]:
            provider = s.get(provider_key, "")
            if not availability.get(provider, False):
                for v in get_missing_env_vars(provider):
                    missing.append(f"{v}  (required for {role}: {PROVIDER_LABELS.get(provider, provider)})")
            if not s.get(name_key):
                missing.append(name_key)

        if s.get("target_type") == "browser":
            if not s.get("browser_config_path"):
                missing.append("browser_config_path")
        else:
            if not s.get("api_endpoint"):
                missing.append("api_endpoint")

        if missing:
            print("The following settings are missing:")
            for m in missing:
                print(f"  - {m}")
            print("Use the 'setting' command to configure them.")
            return False
        return True

    # ------------------------------------------------------------------
    # manual command
    # ------------------------------------------------------------------
    def do_manual(self, arg):
        """Manual Scan – human selects attack methods and runs them exhaustively."""
        if not self._validate_settings():
            return

        catalog = load_atlas_catalog()
        techniques = catalog["techniques"]
        tactics = catalog["tactics"]

        # Build display labels: "[Tactic] ID: Name"
        def _technique_label(tid: str, t: dict) -> str:
            primary_tactic_id = t["tactics"][0]
            tactic_name = tactics.get(primary_tactic_id, {}).get("name", primary_tactic_id)
            return f"[{tactic_name}] {tid}: {t['name']}"

        technique_choices = [_technique_label(tid, t) for tid, t in techniques.items()]
        label_to_id = {_technique_label(tid, t): tid for tid, t in techniques.items()}

        ti_answer = inquirer.prompt([
            inquirer.List("technique", message="Select ATLAS Technique", choices=technique_choices)
        ])
        selected_label = ti_answer["technique"]
        technique_id = label_to_id[selected_label]
        technique = techniques[technique_id]

        # Select attacks from catalog's compatible_attacks
        attack_choices = technique.get("compatible_attacks", [])
        atk_answer = inquirer.prompt([
            inquirer.Checkbox(
                "attacks",
                message=f"Select attacks for {technique_id}: {technique['name']}",
                choices=attack_choices,
                validate=lambda _, c: bool(c) or (_ for _ in ()).throw(
                    inquirer.errors.ValidationError("", reason="Select at least one.")
                ),
            )
        ])
        selected_attacks = atk_answer.get("attacks", [])
        if not selected_attacks:
            print("Operation cancelled.")
            return

        # Load prompts for the selected technique (shared across all attacks)
        dataset_files = technique.get("datasets", [])
        all_prompt_entries: list[dict] = []
        for df in dataset_files:
            all_prompt_entries.extend(load_dataset(df, technique_id))

        if not all_prompt_entries:
            print(f"[!] No prompts found for technique {technique_id}.")
            return

        raw_objectives = select_prompts(all_prompt_entries)

        # Single attacks: apply jailbreak template + response converter once
        has_single = any(a.startswith("Single_") for a in selected_attacks)
        raw_objectives_single = raw_objectives
        if has_single:
            jailbreak = select_jailbreak_methods()
            raw_objectives_single = apply_jailbreak_method(raw_objectives, jailbreak)
            response_enc = select_response_converter()
            raw_objectives_single = apply_response_converter_method(raw_objectives_single, response_enc)

        # Select converters
        converter_names = select_converters()
        converter_instances = instantiate_converters(converter_names)

        ctx = self._build_context(converter_instances)

        async def run_all():
            for attack_name in selected_attacks:
                objectives = raw_objectives_single if attack_name.startswith("Single_") else raw_objectives

                attack = ctx.available_attacks.get(attack_name)
                if attack is None:
                    print(f"[!] Attack not implemented: {attack_name}")
                    continue

                print(f"\n{Fore.BLUE}{'='*60}")
                print(f"[+] Running {attack_name} ({len(objectives)} objective(s))")
                print(f"{'='*60}{Style.RESET_ALL}")

                for objective in objectives:
                    try:
                        result = await attack.run(ctx, objective)
                        result.atlas_techniques = [technique_id]
                        ctx.memory.save_result(result)
                        print_result(result)
                    except Exception as e:
                        print(f"[!] Error in {attack_name}: {e}")

            summary = ctx.memory.summary()
            print(f"\n{Fore.BLUE}{'='*60}")
            print(f"Session summary: {summary['achieved']}/{summary['total']} objectives achieved "
                  f"({summary['rate']:.0%})")
            print(f"{'='*60}{Style.RESET_ALL}")
            await ctx.target.close()

        try:
            asyncio.run(run_all())
        except RuntimeError as e:
            print(f"[!] {e}")

    # ------------------------------------------------------------------
    # agent command
    # ------------------------------------------------------------------
    def do_agent(self, arg):
        """AI Agent Scan – AI agent autonomously selects and executes attacks."""
        if not self._validate_settings():
            return

        # Select converters (optional)
        converter_names = select_converters()
        converter_instances = instantiate_converters(converter_names)

        ctx = self._build_context(converter_instances)

        # Single objective for agent
        obj_answer = inquirer.prompt([
            inquirer.Text("objective", message="Enter the attack objective")
        ])
        objective = obj_answer.get("objective", "").strip()
        if not objective:
            print("Operation cancelled.")
            return

        agent = AttackAgent()

        async def run_agent():
            results = await agent.run(ctx, objective)
            summary = ctx.memory.summary()
            print(f"\n{Fore.BLUE}{'='*60}")
            print(f"Agent session summary: {summary['achieved']}/{summary['total']} achieved "
                  f"({summary['rate']:.0%})")
            print(f"{'='*60}{Style.RESET_ALL}")
            for r in results:
                print_result(r)

        try:
            asyncio.run(run_agent())
        except RuntimeError as e:
            print(f"[!] {e}")

    # ------------------------------------------------------------------
    # setting command
    # ------------------------------------------------------------------
    def do_setting(self, arg):
        """Configure target type, LLM provider/model and connection settings."""
        s = self.settings
        target_type = s.get("target_type", "http")
        availability = get_available_providers()

        print("Current settings:")
        print(f"  Target Type          : {target_type}")
        if target_type == "browser":
            print(f"  Browser Config Path  : {s.get('browser_config_path', '(not set)')}")
        else:
            print(f"  Target API Endpoint  : {s.get('api_endpoint', '(not set)')}")
            print(f"  Body Template        : {s.get('body_template', '(not set)')}")
            print(f"  Response Key         : {s.get('response_key', '(not set)')}")
        print(f"  Adversarial LLM      : [{s.get('adv_llm_provider', 'openai')}] {s.get('adv_llm_name', '(not set)')}")
        print(f"  Score LLM            : [{s.get('score_llm_provider', 'openai')}] {s.get('score_llm_name', '(not set)')}")
        print("-" * 40)

        confirm = inquirer.prompt([
            inquirer.Confirm("update", message="Update settings?", default=True)
        ])
        if not confirm or not confirm.get("update"):
            print("Cancelled.")
            return

        type_answer = inquirer.prompt([
            inquirer.List(
                "target_type",
                message="Target type",
                choices=["http", "browser"],
                default=target_type,
            )
        ])
        new_type = type_answer.get("target_type", "http")

        if new_type == "browser":
            target_answers = inquirer.prompt([
                inquirer.Text(
                    "browser_config_path",
                    message="Browser config YAML path",
                    default=s.get("browser_config_path", ""),
                ),
            ])
        else:
            target_answers = inquirer.prompt([
                inquirer.Text("api_endpoint",  message="Target API endpoint",
                              default=s.get("api_endpoint", "")),
                inquirer.Text("body_template", message='Request body template (use {PROMPT} as placeholder)',
                              default=s.get("body_template", '{"text": "{PROMPT}"}')),
                inquirer.Text("response_key",  message="JSON key to extract response",
                              default=s.get("response_key", "text")),
            ])

        # Build provider choices with availability indicators
        provider_choices = [
            f"{PROVIDER_LABELS[p]}  {'[available]' if availability[p] else '[unavailable: ' + ', '.join(get_missing_env_vars(p)) + ']'}"
            for p in PROVIDER_LABELS
        ]
        provider_keys = list(PROVIDER_LABELS.keys())

        adv_idx = provider_keys.index(s.get("adv_llm_provider", "openai"))
        adv_provider_answer = inquirer.prompt([
            inquirer.List("adv_provider", message="Adversarial LLM provider",
                          choices=provider_choices, default=provider_choices[adv_idx])
        ])
        adv_provider = provider_keys[provider_choices.index(adv_provider_answer["adv_provider"])]

        score_idx = provider_keys.index(s.get("score_llm_provider", "openai"))
        score_provider_answer = inquirer.prompt([
            inquirer.List("score_provider", message="Score LLM provider",
                          choices=provider_choices, default=provider_choices[score_idx])
        ])
        score_provider = provider_keys[provider_choices.index(score_provider_answer["score_provider"])]

        llm_answers = inquirer.prompt([
            inquirer.Text("adv_llm_name",   message=f"Adversarial LLM model name",
                          default=s.get("adv_llm_name", "")),
            inquirer.Text("score_llm_name", message=f"Score LLM model name",
                          default=s.get("score_llm_name", "")),
        ])

        if target_answers and llm_answers:
            self.settings.update({"target_type": new_type})
            self.settings.update(target_answers)
            self.settings["adv_llm_provider"]  = adv_provider
            self.settings["score_llm_provider"] = score_provider
            self.settings.update(llm_answers)
            self.save_settings()

        # Warn if selected provider is unavailable
        for role, provider in [("Adversarial LLM", adv_provider), ("Score LLM", score_provider)]:
            if not availability.get(provider, False):
                missing = get_missing_env_vars(provider)
                print(f"[!] Warning: {role} provider '{PROVIDER_LABELS[provider]}' "
                      f"requires env var(s): {', '.join(missing)}")

    # ------------------------------------------------------------------
    # exit / EOF
    # ------------------------------------------------------------------
    def do_exit(self, arg):
        """Exit the shell."""
        print("Exiting.")
        return True

    def do_EOF(self, arg):
        """Exit with Ctrl-D."""
        print("Exiting.")
        return True

    def help_manual(self):
        print("Run security tests with human-selected attack methods (exhaustive).")

    def help_agent(self):
        print("Run security tests autonomously – the AI agent decides strategy.")

    def help_exit(self):
        print("Exit the shell.")


if __name__ == "__main__":
    import sys
    # ログ初期化は CLI/TUI どちらの起動経路でも最初に走らせる。
    # --debug でレベル DEBUG、それ以外は env var ($PROMPTMAP_LOG_LEVEL) または INFO。
    from engine.logging_setup import setup_logging
    setup_logging(level="DEBUG" if "--debug" in sys.argv else None)

    if "--cli" in sys.argv:
        image_to_colored_ascii_with_promptmap()
        show_random_proverb()
        print("\n")
        print("-+" * 40, "\n")
        PromptMapInteractiveShell().cmdloop()
    else:
        from tui.app import PromptMapApp
        PromptMapApp().run()
