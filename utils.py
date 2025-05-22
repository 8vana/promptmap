import inquirer
import yaml
import pathlib
from typing import List

# Load mapping.
def load_mapping(path="config/mapping.yaml"):
    with open(path, "r") as f:
        return yaml.safe_load(f)

# Load dataset.
def load_dataset(dataset_filename: str, test_category: str) -> List[str]:
    path = pathlib.Path("datasets") / dataset_filename
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    prompts = data.get("prompts", [])
    return [
        entry["value"]
        for entry in prompts
        if test_category in entry.get("categories", [])
    ]

# Dynamically import module names and classes or functions
def get_attack_function(name: str):
    module_name = f"attacks.{name.lower()}"
    func_name   = "run_attack"
    module = __import__(module_name, fromlist=[func_name])
    return getattr(module, func_name)

# Dynamically import converter module names and classes or functions.
def select_converters():
    loaded_yaml = load_mapping("converters/pyrit_converters.yaml")
    converters = loaded_yaml["converters"]

    display_map = {
        f"{c['name']}: {c['description']}": c["name"]
        for c in converters
    }
    choices = list(display_map.keys())

    questions = [
        inquirer.Checkbox(
            "selected",
            message="Select converters to use:",
            choices=choices
        )
    ]
    answers = inquirer.prompt(questions)
    selected_display = answers.get("selected", [])
    # selected_display = ["Base64Converter: プロンプトを Base64 文字列にエンコード／デコードし、ペイロードを隠す。"]
    #selected_display = ["None: コンバーターを使用しない。"]
    #selected_display = ["EmojiConverter: 単語やフレーズを対応する絵文字に置き換え、意味をかいくぐる。"]

    return [display_map[d] for d in selected_display]
