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
    load_mapping, load_dataset, select_prompts,
    select_converters, select_jailbreak_methods, select_response_converter,
    apply_jailbreak_method, apply_response_converter_method, print_result,
)
from converters.instantiate_converters import instantiate_converters

from engine.context import AttackContext
from memory.session_memory import SessionMemory
from targets.http_target import HTTPTargetAdapter
from targets.openai_target import OpenAITargetAdapter
from scorers.llm_judge import LLMJudgeScorer

from attacks.single_pi_attack import SinglePIAttack
from attacks.multi_crescendo_attack import CrescendoAttack
from attacks.multi_pair_attack import PAIRAttack
from attacks.multi_red_teaming_attack import RedTeamingAttack
from attacks.agent.attack_agent import AttackAgent


class PromptMapInteractiveShell(cmd.Cmd):
    intro = f"{Fore.GREEN}Welcome to the 'promptmap' interactive shell! Type help or ? to list commands.{Style.RESET_ALL}\n"
    prompt = f"{Fore.BLUE}(promptmap) {Style.RESET_ALL}"

    config_file = os.path.expanduser("~/.promptmap_config.json")

    settings = {
        "api_endpoint": "",
        "body_template": '{"text": "{PROMPT}"}',
        "response_key": "text",
        "adv_llm_name": "",
        "score_llm_name": "",
    }

    def __init__(self):
        super().__init__()
        self.load_settings()

    def load_settings(self):
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, "r") as f:
                    self.settings.update(json.load(f))
                print("Settings loaded from file.")
            except Exception as e:
                print(f"Failed to load settings: {e}")

        self.settings["adv_llm_api_key"] = os.getenv("ADV_LLM_API_KEY", "")
        if not self.settings["adv_llm_api_key"]:
            print("API Key for adversarial LLM is not set. Please set 'ADV_LLM_API_KEY'.")

        self.settings["score_llm_api_key"] = os.getenv("SCORE_LLM_API_KEY", "")
        if not self.settings["score_llm_api_key"]:
            print("API Key for score LLM is not set. Please set 'SCORE_LLM_API_KEY'.")

    def save_settings(self):
        save_data = {k: v for k, v in self.settings.items()
                     if k not in ("adv_llm_api_key", "score_llm_api_key")}
        try:
            with open(self.config_file, "w") as f:
                json.dump(save_data, f, indent=2)
            print("Settings saved.")
        except Exception as e:
            print(f"Failed to save settings: {e}")

    # ------------------------------------------------------------------
    # Context builder (shared by manual and agent)
    # ------------------------------------------------------------------
    def _build_context(self, converter_instances=None) -> AttackContext:
        s = self.settings

        objective_target = HTTPTargetAdapter(
            endpoint=s["api_endpoint"],
            body_template=json.loads(s["body_template"]),
            response_key=s["response_key"],
        )
        adversarial_target = OpenAITargetAdapter(
            model=s["adv_llm_name"],
            api_key=s["adv_llm_api_key"],
        )
        score_llm = OpenAITargetAdapter(
            model=s["score_llm_name"],
            api_key=s["score_llm_api_key"],
        )
        scorer = LLMJudgeScorer(judge_target=score_llm)
        memory = SessionMemory()

        available_attacks = {
            "Single_PI_Attack":          SinglePIAttack(),
            "Multi_Crescendo_Attack":    CrescendoAttack(),
            "Multi_PAIR_Attack":         PAIRAttack(),
            "Multi_Red_Teaming_Attack":  RedTeamingAttack(),
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
        required = {
            "api_endpoint":    self.settings.get("api_endpoint"),
            "adv_llm_name":    self.settings.get("adv_llm_name"),
            "adv_llm_api_key": self.settings.get("adv_llm_api_key"),
            "score_llm_name":  self.settings.get("score_llm_name"),
            "score_llm_api_key": self.settings.get("score_llm_api_key"),
        }
        missing = [k for k, v in required.items() if not v]
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

        mapping = load_mapping()

        # Select test item
        test_items = list(mapping["test_items"].keys())
        ti_answer = inquirer.prompt([
            inquirer.List("test_item", message="Select Test Item", choices=test_items)
        ])
        ti = ti_answer["test_item"]

        # Select attacks
        attack_choices = mapping["test_items"][ti]
        atk_answer = inquirer.prompt([
            inquirer.Checkbox(
                "attacks",
                message=f"Select attacks for {ti}",
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

        # Select converters
        converter_names = select_converters()
        converter_instances = instantiate_converters(converter_names)

        ctx = self._build_context(converter_instances)

        async def run_all():
            for attack_name in selected_attacks:
                dataset_file = mapping["attack_datasets"].get(attack_name)
                if not dataset_file:
                    print(f"[!] No dataset configured for {attack_name}")
                    continue

                raw_objectives = select_prompts(load_dataset(dataset_file, ti))

                # Single attacks: apply jailbreak template + response converter
                if attack_name.startswith("Single_"):
                    jailbreak = select_jailbreak_methods()
                    raw_objectives = apply_jailbreak_method(raw_objectives, jailbreak)
                    response_enc = select_response_converter()
                    raw_objectives = apply_response_converter_method(raw_objectives, response_enc)

                attack = ctx.available_attacks.get(attack_name)
                if attack is None:
                    print(f"[!] Attack not implemented: {attack_name}")
                    continue

                print(f"\n{Fore.BLUE}{'='*60}")
                print(f"[+] Running {attack_name} ({len(raw_objectives)} objective(s))")
                print(f"{'='*60}{Style.RESET_ALL}")

                for objective in raw_objectives:
                    try:
                        result = await attack.run(ctx, objective)
                        ctx.memory.save_result(result)
                        print_result(result)
                    except Exception as e:
                        print(f"[!] Error in {attack_name}: {e}")

            summary = ctx.memory.summary()
            print(f"\n{Fore.BLUE}{'='*60}")
            print(f"Session summary: {summary['achieved']}/{summary['total']} objectives achieved "
                  f"({summary['rate']:.0%})")
            print(f"{'='*60}{Style.RESET_ALL}")

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
        """Configure API endpoint, LLM names, body template and response key."""
        s = self.settings
        print("Current settings:")
        print(f"  Target API Endpoint : {s.get('api_endpoint', '(not set)')}")
        print(f"  Body Template       : {s.get('body_template', '(not set)')}")
        print(f"  Response Key        : {s.get('response_key', '(not set)')}")
        print(f"  Adversarial LLM     : {s.get('adv_llm_name', '(not set)')}")
        print(f"  Score LLM           : {s.get('score_llm_name', '(not set)')}")
        print("-" * 40)

        confirm = inquirer.prompt([
            inquirer.Confirm("update", message="Update settings?", default=True)
        ])
        if not confirm or not confirm.get("update"):
            print("Cancelled.")
            return

        answers = inquirer.prompt([
            inquirer.Text("api_endpoint",  message="Target API endpoint",
                          default=s.get("api_endpoint", "")),
            inquirer.Text("body_template", message='Request body template (use {PROMPT} as placeholder)',
                          default=s.get("body_template", '{"text": "{PROMPT}"}')),
            inquirer.Text("response_key",  message="JSON key to extract response",
                          default=s.get("response_key", "text")),
            inquirer.Text("adv_llm_name",  message="Adversarial LLM name (e.g. gpt-4o-mini)",
                          default=s.get("adv_llm_name", "")),
            inquirer.Text("score_llm_name", message="Score LLM name (e.g. gpt-4o-mini)",
                          default=s.get("score_llm_name", "")),
        ])
        if answers:
            self.settings.update(answers)
            self.save_settings()

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
    if "--cli" in sys.argv:
        image_to_colored_ascii_with_promptmap()
        show_random_proverb()
        print("\n")
        print("-+" * 40, "\n")
        PromptMapInteractiveShell().cmdloop()
    else:
        from tui.app import PromptMapApp
        PromptMapApp().run()
