import importlib
from typing import List
from pyrit.prompt_converter import PromptConverter

# Default arguments of any converters.
DEFAULT_CONVERTER_ARGS = {
    "RandomCapitalLettersConverter": {"percentage": 25.0},
    "CaesarConverter": {"shift": 3},
    "CharSwapGenerator": {"swap_probability": 0.1},
}

def instantiate_converters(names: List[str]) -> List[PromptConverter]:
    instances: List[PromptConverter] = []
    module = importlib.import_module("pyrit.prompt_converter")

    for name in names:
        if name == 'None':
            break

        try:
            # Get class object.
            cls = getattr(module, name)
        except AttributeError:
            raise ValueError(f"Unknown converter: {name}")

        # Get default arguments if necessary.
        kwargs = DEFAULT_CONVERTER_ARGS.get(name, {})

        try:
            inst = cls(**kwargs)
        except TypeError as e:
            raise TypeError(f"Failed to instantiate {name} with args {kwargs}: {e}")

        instances.append(inst)

    return instances
