import importlib
from typing import List

from converters.base_converter import BaseConverter, PyRITConverterAdapter

DEFAULT_CONVERTER_ARGS = {
    "RandomCapitalLettersConverter": {"percentage": 25.0},
    "CaesarConverter": {"shift": 3},
    "CharSwapGenerator": {"swap_probability": 0.1},
}


def instantiate_converters(names: List[str]) -> List[BaseConverter]:
    """Instantiate PyRIT converters and wrap them as BaseConverter adapters."""
    instances: List[BaseConverter] = []
    module = importlib.import_module("pyrit.prompt_converter")

    for name in names:
        if name == "None":
            break

        try:
            cls = getattr(module, name)
        except AttributeError:
            raise ValueError(f"Unknown converter: {name}")

        kwargs = DEFAULT_CONVERTER_ARGS.get(name, {})

        try:
            pyrit_instance = cls(**kwargs)
        except TypeError as e:
            raise TypeError(f"Failed to instantiate {name} with args {kwargs}: {e}")

        instances.append(PyRITConverterAdapter(pyrit_instance))

    return instances
