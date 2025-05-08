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
        if test_category in entry.get("test_categories", [])
    ]

# Dynamically import module names and classes or functions
def get_attack_function(name: str):
    module_name = f"attacks.{name.lower()}"
    func_name   = "run_attack"
    module = __import__(module_name, fromlist=[func_name])
    return getattr(module, func_name)
