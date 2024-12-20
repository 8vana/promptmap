import os
import importlib
import pathlib

ATTACKS_MAPPING = {}

# Get the path of the attacks directory.
attacks_dir = pathlib.Path(__file__).parent

# Scan all .py files in the attacks directory.
for file in attacks_dir.glob("*.py"):
    if file.name == "__init__.py":
        continue  # Skip "__init__.py"
    module_name = file.stem  # The part of the file name excluding the extension
    try:
        # Importing a module.
        module = importlib.import_module(f".{module_name}", package="attacks")
        # Retrieve TEST_ITEM_NAME and run_attack.
        test_item_name = getattr(module, "TEST_ITEM_NAME", None)
        run_attack = getattr(module, "run_attack", None)
        if test_item_name and run_attack:
            ATTACKS_MAPPING[test_item_name] = run_attack
    except Exception as e:
        print(f"[!] Failed to load attack module '{module_name}': {e}")
