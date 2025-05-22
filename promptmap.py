import os
import cmd
import json
import inquirer
import asyncio
from colorama import init, Fore, Style
init(autoreset=True)

from ascii_art import image_to_colored_ascii_with_promptmap
from proverb import show_random_proverb
from converters.instantiate_converters import instantiate_converters
from utils import load_mapping, load_dataset, get_attack_function, select_converters

from pyrit.common import initialize_pyrit, DUCK_DB
from pyrit.memory import DuckDBMemory
from pyrit.prompt_target import HTTPTarget, get_http_target_json_response_callback_function, OpenAIChatTarget


class PromptMapInteractiveShell(cmd.Cmd):
    intro = f"{Fore.GREEN}Welcome to the 'promptmap' interactive shell! Type help or ? to list commands.{Style.RESET_ALL}\n"
    prompt = f"{Fore.BLUE}(promptmap) {Style.RESET_ALL}"

    # Set the path of the configuration file (saved in the user directory).
    config_file = os.path.expanduser('~/.promptmap_config.json')

    # Dictionary that retains settings.
    settings = {
        'api_endpoint': '',
        'llm_name': ''
    }

    def __init__(self):
        super().__init__()
        # Load settings when starting up the shell.
        self.load_settings()

    def load_settings(self):
        """Load settings from a file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    self.settings = json.load(f)
                print("Settings loaded from file.")
            except Exception as e:
                print(f"Failed to load settings: {e}")
                return True

        # API key is obtained from the environment variable.
        self.settings['adv_llm_api_key'] = os.getenv('ADV_LLM_API_KEY', '')
        if not self.settings['adv_llm_api_key']:
            print("API Key for adversarial llm is not set. Please set the 'ADV_LLM_API_KEY' environment variable.")
            return True
        self.settings['score_llm_api_key'] = os.getenv('SCORE_LLM_API_KEY', '')
        if not self.settings['score_llm_api_key']:
            print("API Key for score llm is not set. Please set the 'SCORE_LLM_API_KEY' environment variable.")
            return True

    def save_settings(self):
        """Save settings to a file."""
        settings_copy = self.settings.copy()

        # API key is not saved.
        settings_copy.pop('adv_llm_api_key', None)
        settings_copy.pop('score_llm_api_key', None)
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.settings, f)
            print("Settings have been saved to file.")
        except Exception as e:
            print(f"Failed to save settings: {e}")
            return True

    # ----- Basic commands -----
    def do_standard(self, arg):
        """Standard Scan"""
        target_api_endpoint = self.settings.get('api_endpoint')
        adv_llm_name = self.settings.get('adv_llm_name')
        adv_llm_api_key = self.settings.get('adv_llm_api_key')
        score_llm_name = self.settings.get('score_llm_name')
        score_llm_api_key = self.settings.get('score_llm_api_key')

        # If the settings have not been entered, a warning will be displayed.
        config_values = {
            'target_api_endpoint': target_api_endpoint,
            'adv_llm_name': adv_llm_name,
            'adv_llm_api_key': adv_llm_api_key,
            'score_llm_name': score_llm_name,
            'score_llm_api_key': score_llm_api_key,
        }
        missing_values = [name for name, val in config_values.items() if not val]
        if missing_values:
            print("The following settings are missing:")
            for missing_value in missing_values:
                print(f"  - {missing_value}")
            print("Please set up the configurations using the 'setting' command before proceeding.")
            return

        # Define Adversarial LLM.
        adversarial_target = OpenAIChatTarget(
            endpoint="https://api.openai.com/v1/chat/completions",
            model_name=adv_llm_name,
            api_key=adv_llm_api_key
        )

        # Define Scoring LLM.
        scoring_target = OpenAIChatTarget(
            endpoint="https://api.openai.com/v1/chat/completions",
            model_name=score_llm_name,
            api_key=score_llm_api_key
        )

        # Define HTTP request and target endpoint (Must be changed according to the app being tested).
        '''
        # http://localhost:11434/api/generate
        raw_http_request = f"""
            POST {target_api_endpoint} HTTP/1.1
            Content-Type: application/json

            {{
                "model": "llama3.2",
                "prompt": "{{PROMPT}}",
                "stream": false
            }}
        """
        '''
        #http://localhost:8000/prompt-leaking-lv1
        raw_http_request = f"""
            POST {target_api_endpoint} HTTP/1.1
            Content-Type: application/json

            {{
                "text": "{{PROMPT}}"
            }}
        """
        #parsing_fn = get_http_target_json_response_callback_function(key="response")
        parsing_fn = get_http_target_json_response_callback_function(key="text")
        objective_target = HTTPTarget(http_request=raw_http_request, callback_function=parsing_fn, timeout=300.0)

        # Here, the processing of the standard command is described.
        print(f"Using API Endpoint: {target_api_endpoint}")
        print(f"Using Adversarial LLM: {adv_llm_name}")
        print(f"Using Score LLM: {score_llm_name}")

        # Retrieve dynamically generated test_items.
        mapping = load_mapping()

        # Select test items.
        test_items = list(mapping["test_items"].keys())
        answers = inquirer.prompt([
            inquirer.List(
                "test_item",
                message="Select Test Item",
                choices=test_items
            )
        ])
        ti = answers["test_item"]

        # Select the attack method corresponding to the test item.
        attacks = mapping["test_items"][ti]
        answers = inquirer.prompt([
             inquirer.Checkbox(
                "attacks",
                message=f"Select attacks for {ti}",
                choices=attacks
            )
        ])
        selected_attacks = answers["attacks"]
        # selected_attacks = ['Single_PI_Attack']
        # selected_attacks = ['Multi_Crescendo_Attack']

        # Select converters.
        converters_map = select_converters()
        converter_instances = instantiate_converters(converters_map)

        # Processing the results.
        if answers and "attacks" in answers:
            # Internal function for asynchronous execution of attacks.
            async def run_attacks(selected_attacks, http_prompt_target):
                for attack_name in selected_attacks:
                    dataset_file = mapping["attack_datasets"][attack_name]
                    prompts = load_dataset(dataset_file, ti)
                    attack_function = get_attack_function(attack_name)
                    print(f"\n[+] Running {attack_name} with dataset {dataset_file} ({len(prompts)} prompts)")

                    if attack_function:
                        print(f"\n[+] Executing attack: {attack_name}")
                        try:
                            if "Single_" in attack_name:
                                await attack_function(
                                    http_prompt_target,
                                    prompts,
                                    scoring_target,
                                    converter_instances
                                )
                            elif "Multi_" in attack_name:
                                await attack_function(
                                    http_prompt_target,
                                    prompts,
                                    adversarial_target,
                                    scoring_target,
                                    converter_instances
                                )
                            else:
                                raise ValueError("The name of the attack method is invalid.")
                        except Exception as e:
                            print(f"[!] Error executing {attack_name}: {e}")
                    else:
                        print(f"[!] No attack function found for: {attack_name}")

            # Executing an asynchronous function.
            try:
                asyncio.run(run_attacks(selected_attacks, objective_target))
            except RuntimeError as e:
                print(f"[!] Failed to execute attacks: {e}")
        else:
            print("Operation cancelled.")

    def do_agent(self, arg):
        """AI Agent Scan"""
        print("Coming soon.")

    def do_setting(self, arg):
        """Set up configurations: API endpoint, LLM name, API Key and Parsing response"""
        # Display current settings.
        print("Current settings:")
        print(f"Target API Endpoint: {self.settings.get('api_endpoint', '(not set)')}")
        print(f"Adversarial LLM Name: {self.settings.get('llm_name', '(not set)')}")
        api_key_display = '*' * len(self.settings.get('api_key', '')) if self.settings.get('api_key') else '(not set)'
        print(f"API Key for Adversarial LLM: {api_key_display}")
        print(f"Regex of parsing response: {self.settings.get('regex_key', '(not set)')}")
        print("-" * 40)

        # Confirm whether to update the settings.
        questions = [
            inquirer.Confirm(
                'update_settings',
                message='Do you want to update the settings?',
                default=True
            )
        ]
        answers = inquirer.prompt(questions)
        if not answers or not answers.get('update_settings'):
            print("Settings update cancelled.")
            return

        questions = [
            inquirer.Text(
                'api_endpoint',
                message='Enter the target API endpoint of the system under test',
                default=self.settings.get('api_endpoint', '')
            ),
            inquirer.Text(
                'adv_llm_name',
                message='Enter the name of the Adversarial LLM to use (e.g., gpt-4o-mini)',
                default=self.settings.get('adv_llm_name', '')
            ),
            inquirer.Text(
                'score_llm_name',
                message='Enter the name of the Score LLM to use (e.g., gpt-4o-mini)',
                default=self.settings.get('score_llm_name', '')
            )
        ]
        answers = inquirer.prompt(questions)

        # DEBUG
        # answers = {'adv_llm_name': 'gpt-4o-mini', 'api_endpoint': 'http://localhost:11434/api/generate', 'score_llm_name': 'gpt-4o-mini'}
        if answers:
            self.settings.update(answers)
            self.save_settings()
            print("Settings have been updated:")
            print(f"Target API Endpoint: {self.settings['api_endpoint']}")
            print(f"Adversarial LLM Name: {self.settings['adv_llm_name']}")
            print(f"Score LLM Name: {self.settings['score_llm_name']}")
        else:
            print("Settings update cancelled.")

    def do_exit(self, arg):
        """Exit the shell: EXIT"""
        print('Exiting the shell.')
        return True

    def do_EOF(self, arg):
        """Exit the shell with Ctrl-D"""
        print('Exiting the shell.')
        return True

    def help_standard(self):
        print("""
        This menu is a mode where you can select the test items and run the test.
        """)

    def help_agent(self):
        print("""
        This menu is a mode in which the autonomous AI agent automatically performs all tests.
        """)

    def help_exit(self):
        print('Exit the shell.')


if __name__ == '__main__':
    # Show banner.
    image_to_colored_ascii_with_promptmap()
    show_random_proverb()
    print("\n")
    print("-+"*40, "\n")

    # Initialize memory.
    initialize_pyrit(memory_db_type=DUCK_DB)
    memory = DuckDBMemory()

    # Launch interactive shell.
    PromptMapInteractiveShell().cmdloop()
