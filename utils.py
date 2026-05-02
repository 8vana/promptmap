import pathlib
import yaml
import inquirer
from typing import List
from inquirer.errors import ValidationError
from colorama import Fore, Style

from engine.models import AttackResult

FREE_ENTRY_TAG = "** Free entry **"


def at_least_one(answers, current_selection):
    if not current_selection:
        raise ValidationError("", reason="Please select one or more options.")
    return True


def load_mapping(path: str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_atlas_catalog(path="config/atlas_catalog.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_dataset(dataset_filename: str, atlas_technique_id: str) -> List[dict]:
    path = pathlib.Path("datasets") / dataset_filename
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    return [
        {
            "value": entry["value"],
            "prompt_technique": entry.get("prompt_technique", ""),
        }
        for entry in data.get("prompts", [])
        if atlas_technique_id in entry.get("atlas_techniques", [])
    ]


def enter_any_prompt(selected_prompts):
    if FREE_ENTRY_TAG not in selected_prompts:
        return selected_prompts
    free_text_cache = None
    formatted = []
    for item in selected_prompts:
        if item == FREE_ENTRY_TAG:
            while not free_text_cache:
                free_text_cache = input("Enter your custom prompt: ").strip()
                if not free_text_cache:
                    print("Input is empty. Please try again.")
            formatted.append(free_text_cache)
        else:
            formatted.append(item)
    return formatted


def apply_jailbreak_method(prompts, jailbreak_template=None):
    if jailbreak_template is None:
        return prompts
    return [jailbreak_template.replace("{{ prompt }}", p) for p in prompts]


def apply_response_converter_method(prompts, response_converter=None):
    if response_converter is None:
        return prompts
    return [f"{p}\n\n{response_converter}" for p in prompts]


def select_prompts(prompt_entries: List[dict]) -> List[str]:
    display_to_value: dict[str, str] = {}
    for entry in prompt_entries:
        tech = entry.get("prompt_technique", "")
        display = f"[{tech}] {entry['value']}" if tech else entry["value"]
        display_to_value[display] = entry["value"]

    choices = [FREE_ENTRY_TAG] + sorted(display_to_value.keys())
    answers = inquirer.prompt([
        inquirer.Checkbox(
            "selected",
            message="Select adversarial prompts to use:",
            choices=choices,
            validate=at_least_one,
        )
    ])
    resolved = []
    for item in answers.get("selected", []):
        resolved.append(FREE_ENTRY_TAG if item == FREE_ENTRY_TAG else display_to_value.get(item, item))
    return enter_any_prompt(resolved)


def select_converters():
    loaded_yaml = load_mapping("converters/pyrit_converters.yaml")
    converters = loaded_yaml["converters"]
    display_map = {f"{c['name']}: {c['description']}": c["name"] for c in converters}
    answers = inquirer.prompt([
        inquirer.Checkbox(
            "selected",
            message="Select converters to use:",
            choices=list(display_map.keys()),
            validate=at_least_one,
        )
    ])
    return [display_map[d] for d in answers.get("selected", [])]


def select_jailbreak_methods():
    NONE_TAG = "[none] No jailbreak template"
    builtin_dir = _pyrit_jailbreak_dir()
    custom_dir = pathlib.Path("datasets/custom_jailbreaks").expanduser()

    allowed = load_mapping("datasets/jailbreak_config.yaml")
    builtin_choices = [
        f"[builtin] {fn}"
        for fn in allowed.get("builtin_templates", [])
        if builtin_dir and (builtin_dir / fn).is_file()
    ]
    custom_choices = []
    if custom_dir.exists():
        custom_choices = [f"[custom] {p.name}" for p in sorted(custom_dir.glob("*.yaml"))]

    choices = [NONE_TAG] + builtin_choices + custom_choices

    answers = inquirer.prompt([
        inquirer.List("template", message="Select jailbreak template:", choices=choices)
    ]) or {}
    selected = answers.get("template", NONE_TAG)

    if selected == NONE_TAG:
        return None

    tag, fname = selected.split(" ", 1)
    path = (builtin_dir / fname) if tag == "[builtin]" else (custom_dir / fname)
    return _load_jailbreak_value(path)


def select_response_converter():
    loaded_yaml = load_mapping("datasets/response_encode.yaml")
    prompts = loaded_yaml["prompts"]
    display_map = {f"{c['name']}: {c['value']}": c["value"] for c in prompts}

    choices = [FREE_ENTRY_TAG] + list(display_map.keys())
    answers = inquirer.prompt([
        inquirer.List("selected", message="Select response converter:", choices=choices)
    ])
    selected_prompt = answers.get("selected", "")
    result = enter_any_prompt([selected_prompt])
    return display_map.get(result[0]) if result[0] != FREE_ENTRY_TAG else result[0]


def print_result(result: AttackResult) -> None:
    sep = "=" * 60
    status = f"{Fore.RED}ACHIEVED ✓{Style.RESET_ALL}" if result.achieved else f"{Fore.GREEN}not achieved ✗{Style.RESET_ALL}"
    print(f"\n{Fore.BLUE}{sep}{Style.RESET_ALL}")
    print(f"Attack   : {result.attack_name}")
    print(f"Objective: {result.objective[:120]}")
    print(f"Result   : {status}")
    print(f"Score    : {result.score:.2f}  |  Turns: {result.turns}")
    print(f"{Fore.BLUE}{sep}{Style.RESET_ALL}")
    for msg in result.conversation:
        label = f"{Fore.CYAN}[User]{Style.RESET_ALL}      " if msg.role == "user" else f"{Fore.YELLOW}[Assistant]{Style.RESET_ALL}"
        body = msg.content[:300] + ("..." if len(msg.content) > 300 else "")
        print(f"\n{label}: {body}")
    print(f"{Fore.BLUE}{sep}{Style.RESET_ALL}\n")


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------
def _pyrit_jailbreak_dir():
    return pathlib.Path("datasets/builtin_jailbreaks")


def _load_jailbreak_value(path: pathlib.Path) -> str:
    with open(path, "r") as f:
        data = yaml.safe_load(f)
    # SeedPrompt YAML has a top-level 'value' field
    return data.get("value", "")
