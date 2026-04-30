from typing import List

from converters.base_converter import BaseConverter
from converters.native_converters import get_converter_class

DEFAULT_CONVERTER_ARGS = {
    "RandomCapitalLettersConverter": {"percentage": 25.0},
    "CaesarConverter":               {"caesar_offset": 3},
    "CharSwapGenerator":             {"word_swap_ratio": 0.1},
}


def instantiate_converters(names: List[str]) -> List[BaseConverter]:
    """Instantiate native converters by name and return as BaseConverter list."""
    instances: List[BaseConverter] = []

    for name in names:
        if name == "None":
            break

        cls = get_converter_class(name)
        kwargs = DEFAULT_CONVERTER_ARGS.get(name, {})

        try:
            instances.append(cls(**kwargs))
        except TypeError as e:
            raise TypeError(f"Failed to instantiate {name} with args {kwargs}: {e}")

    return instances
