import os
import cmd
import json
import inquirer
import asyncio
from colorama import init, Fore, Style
init(autoreset=True)

from targets import custom_web_api_target
from attacks import ATTACKS_MAPPING
from ascii_art import image_to_colored_ascii_with_promptmap
from proverb import show_random_proverb


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
        self.settings['api_key'] = os.getenv('LLM_API_KEY', '')
        if not self.settings['api_key']:
            print("API Key is not set. Please set the 'LLM_API_KEY' environment variable.")
            return True

    def save_settings(self):
        """Save settings to a file."""
        settings_copy = self.settings.copy()
        settings_copy.pop('api_key', None)  # API key is not saved.
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
        attack_llm_name = self.settings.get('llm_name')
        attack_llm_api_key = self.settings.get('api_key')
        regex_key = self.settings.get('regex_key')

        # Debug.
        #target_api_endpoint = 'http://localhost:8000/prompt-leaking-lv1'
        #attack_llm_name = 'gpt-4o-mini'
        #attack_llm_api_key = 'xxx'
        #regex_key = r'\"text\"\s*\:\s*\"(.*)\"'
        raw_http_req = f"""
        POST {target_api_endpoint} HTTP/1.1
        Content-Type: application/json

        {{
            "text":"{{PROMPT}}"
        }}
        """

        # If the settings have not been entered, a warning will be displayed.
        if not target_api_endpoint or not attack_llm_name or not attack_llm_api_key:
            print("Please set up the configurations using the 'setting' command before proceeding.")
            return

        # Here, the processing of the standard command is described.
        print(f"Using API Endpoint: {target_api_endpoint}")
        print(f"Using LLM: {attack_llm_name}")

        # Retrieve dynamically generated test_items.
        test_items = list(ATTACKS_MAPPING.keys())

        # Display a prompt with a checkbox using inquirer.
        questions = [
            inquirer.Checkbox(
                'selected_items',
                message='Please select test items:',
                choices=test_items,
            )
        ]

        # Prompts the user to respond.
        answers = inquirer.prompt(questions)

        # Processing the results.
        answers['selected_items'] = ['Basic Prompt Injection']
        if answers and 'selected_items' in answers:
            selected_items = answers['selected_items']
            if selected_items:
                print("You have selected test item:")
                for item in test_items:
                    if item in selected_items:
                        print(f"[*]: {item}")

                # Generate targets using a standardized method.
                http_prompt_target = custom_web_api_target.HTTPTargetManager(
                    endpoint_url=target_api_endpoint,
                    regex_key=regex_key,
                    http_req=raw_http_req
                )

                # Internal function for asynchronous execution of attacks.
                async def run_attacks(selected_items, http_prompt_target):
                    for item in selected_items:
                        attack_function = ATTACKS_MAPPING.get(item)
                        if attack_function:
                            print(f"\n[+] Executing attack: {item}")
                            try:
                                await attack_function(http_prompt_target)
                            except Exception as e:
                                print(f"[!] Error executing {item}: {e}")
                        else:
                            print(f"[!] No attack function found for: {item}")

                # Executing an asynchronous function.
                try:
                    asyncio.run(run_attacks(selected_items, http_prompt_target))
                except RuntimeError as e:
                    print(f"[!] Failed to execute attacks: {e}")
            else:
                print("No test items selected.")
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
        print(f"Attack LLM Name: {self.settings.get('llm_name', '(not set)')}")
        api_key_display = '*' * len(self.settings.get('api_key', '')) if self.settings.get('api_key') else '(not set)'
        print(f"API Key for Attack LLM: {api_key_display}")
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
                'llm_name',
                message='Enter the name of the Attack LLM to use (e.g., gpt-4o-mini)',
                default=self.settings.get('llm_name', '')
            ),
            inquirer.Text(
                'regex_key',
                message='Enter the regex of parsing the response from the test target　(e.g., \"text\"\s*\:\s*\"(.*)\")',
                default=self.settings.get('regex_key', '')
            ),
        ]

        answers = inquirer.prompt(questions)

        if answers:
            self.settings.update(answers)
            self.save_settings()
            print("Settings have been updated:")
            print(f"Target API Endpoint: {self.settings['api_endpoint']}")
            print(f"Attack LLM Name: {self.settings['llm_name']}")
            print(f"Regex key: {self.settings['regex_key']}")
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

    # Launch interactive shell.
    PromptMapInteractiveShell().cmdloop()
