"""Native converter implementations — stdlib only, no PyRIT dependency."""
import base64
import codecs
import math
import random
import re
import string
import urllib.parse
from typing import Dict, List, Optional

from converters.base_converter import BaseConverter


class AnsiAttackConverter(BaseConverter):
    """Inserts ANSI escape sequences at word boundaries to confuse terminal/log parsers."""

    _SEQUENCES = [
        "\x1b[0m", "\x1b[1m", "\x1b[31m", "\x1b[32m", "\x1b[33m",
        "\x1b[2J", "\x1b[H", "\x1b[?25l",
    ]

    async def convert(self, prompt: str) -> str:
        words = prompt.split()
        result = []
        for word in words:
            result.append(word)
            if random.random() < 0.3:
                result.append(random.choice(self._SEQUENCES))
        return " ".join(result)


class AsciiSmugglerConverter(BaseConverter):
    """Encodes ASCII printable characters using the Unicode Tags block (U+E0000+n).

    The encoded text is invisible in most renderers but preserved in the byte stream,
    bypassing content filters that operate on visible text.
    Reference: https://embracethered.com/blog/posts/2024/hiding-and-finding-text-with-unicode-tags/
    """

    async def convert(self, prompt: str) -> str:
        return "".join(
            chr(0xE0000 + ord(c)) if 0x20 <= ord(c) <= 0x7E else c
            for c in prompt
        )


class AtbashConverter(BaseConverter):
    """Atbash cipher: A↔Z, a↔z, 0↔9."""

    _TABLE = str.maketrans(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",
        "ZYXWVUTSRQPONMLKJIHGFEDCBAzyxwvutsrqponmlkjihgfedcba9876543210",
    )

    def __init__(self, *, append_description: bool = False) -> None:
        self.append_description = append_description

    async def convert(self, prompt: str) -> str:
        result = prompt.translate(self._TABLE)
        if self.append_description:
            result += (
                "\n\n(Atbash cipher — A↔Z, B↔Y, …  "
                "Please decode and respond using the same cipher.)"
            )
        return result


class Base64Converter(BaseConverter):
    """Encodes the prompt as a Base64 string."""

    async def convert(self, prompt: str) -> str:
        return base64.b64encode(prompt.encode("utf-8")).decode("utf-8")


class BinaryConverter(BaseConverter):
    """Converts each character to its binary representation (space-separated words)."""

    def __init__(self, bits_per_char: int = 16) -> None:
        if bits_per_char not in (8, 16, 32):
            raise ValueError("bits_per_char must be 8, 16, or 32")
        self.bits_per_char = bits_per_char

    async def convert(self, prompt: str) -> str:
        return " ".join(format(ord(c), f"0{self.bits_per_char}b") for c in prompt)


class CaesarConverter(BaseConverter):
    """Caesar cipher — shifts letters by a fixed offset; digits shifted if offset < 10."""

    def __init__(self, *, caesar_offset: int = 3, append_description: bool = False) -> None:
        self._offset = caesar_offset % 26
        self._digit_offset = caesar_offset if caesar_offset < 10 else 0
        self.append_description = append_description

    def _shift(self, c: str) -> str:
        if c.isupper():
            return chr((ord(c) - ord("A") + self._offset) % 26 + ord("A"))
        if c.islower():
            return chr((ord(c) - ord("a") + self._offset) % 26 + ord("a"))
        if c.isdigit() and self._digit_offset:
            return str((int(c) + self._digit_offset) % 10)
        return c

    async def convert(self, prompt: str) -> str:
        result = "".join(self._shift(c) for c in prompt)
        if self.append_description:
            result += f"\n\n(Caesar cipher, offset={self._offset})"
        return result


class CharSwapGenerator(BaseConverter):
    """Randomly swaps adjacent characters within a proportion of words."""

    def __init__(self, *, max_iterations: int = 10, word_swap_ratio: float = 0.2) -> None:
        if max_iterations <= 0:
            raise ValueError("max_iterations must be > 0")
        if not (0 < word_swap_ratio <= 1):
            raise ValueError("word_swap_ratio must be in (0, 1]")
        self.max_iterations = max_iterations
        self.word_swap_ratio = word_swap_ratio

    def _perturb(self, word: str) -> str:
        if word not in string.punctuation and len(word) > 3:
            idx = random.randint(1, len(word) - 2)
            chars = list(word)
            chars[idx], chars[idx + 1] = chars[idx + 1], chars[idx]
            return "".join(chars)
        return word

    async def convert(self, prompt: str) -> str:
        words = re.findall(r"\w+|\S+", prompt)
        num_perturb = max(1, math.ceil(len(words) * self.word_swap_ratio))
        indices = random.sample(range(len(words)), min(num_perturb, len(words)))
        for _ in range(self.max_iterations):
            for i in indices:
                words[i] = self._perturb(words[i])
        return " ".join(words)


class CharacterSpaceConverter(BaseConverter):
    """Inserts a space between every character and removes punctuation.

    Reference: https://www.robustintelligence.com/blog-posts/bypassing-metas-llama-classifier-a-simple-jailbreak
    """

    async def convert(self, prompt: str) -> str:
        return re.sub(r'[!"#$%&\'()*+,\-./:;<=>?@\[\\\]^_`{|}~]', "", " ".join(prompt))


class ColloquialWordswapConverter(BaseConverter):
    """Substitutes common English words with Singaporean colloquial equivalents."""

    _DEFAULT: Dict[str, List[str]] = {
        "father":      ["papa", "lao bei", "lim pei", "bapa", "appa"],
        "mother":      ["mama", "amma", "ibu"],
        "grandfather": ["ah gong", "thatha", "dato"],
        "grandmother": ["ah ma", "patti", "nenek"],
        "girl":        ["ah ger", "ponnu"],
        "boy":         ["ah boy", "boi", "payyan"],
        "son":         ["ah boy", "boi", "payyan"],
        "daughter":    ["ah ger", "ponnu"],
        "aunt":        ["makcik", "maami"],
        "aunty":       ["makcik", "maami"],
        "man":         ["ah beng", "shuai ge"],
        "woman":       ["ah lian", "xiao mei"],
        "uncle":       ["encik", "unker"],
        "sister":      ["xjj", "jie jie", "zhezhe", "kaka", "akka", "thangatchi"],
        "brother":     ["bro", "boiboi", "di di", "xdd", "anneh", "thambi"],
    }

    def __init__(
        self,
        deterministic: bool = False,
        custom_substitutions: Optional[Dict[str, List[str]]] = None,
    ) -> None:
        self._subs = custom_substitutions if custom_substitutions else self._DEFAULT
        self._deterministic = deterministic

    async def convert(self, prompt: str) -> str:
        words = re.findall(r"\w+|\S+", prompt)
        result = []
        for w in words:
            opts = self._subs.get(w.lower())
            if opts:
                result.append(opts[0] if self._deterministic else random.choice(opts))
            else:
                result.append(w)
        return " ".join(result)


class EmojiConverter(BaseConverter):
    """Replaces letters with circled/squared emoji-letter variants.

    Uses a built-in lookup table — no external emoji library required.
    Reference: https://github.com/BASI-LABS/parseltongue
    """

    _MAP: Dict[str, List[str]] = {
        "a": ["🅐", "🅰️", "🄰"], "b": ["🅑", "🅱️", "🄱"], "c": ["🅒", "🅲", "🄲"],
        "d": ["🅓", "🅳", "🄳"], "e": ["🅔", "🅴", "🄴"], "f": ["🅕", "🅵", "🄵"],
        "g": ["🅖", "🅶", "🄶"], "h": ["🅗", "🅷", "🄷"], "i": ["🅘", "🅸", "🄸"],
        "j": ["🅙", "🅹", "🄹"], "k": ["🅚", "🅺", "🄺"], "l": ["🅛", "🅻", "🄻"],
        "m": ["🅜", "🅼", "🄼"], "n": ["🅝", "🅽", "🄽"], "o": ["🅞", "🅾️", "🄾"],
        "p": ["🅟", "🅿️", "🄿"], "q": ["🅠", "🆀", "🅀"], "r": ["🅡", "🆁", "🅁"],
        "s": ["🅢", "🆂", "🅂"], "t": ["🅣", "🆃", "🅃"], "u": ["🅤", "🆄", "🅄"],
        "v": ["🅥", "🆅", "🅅"], "w": ["🅦", "🆆", "🅆"], "x": ["🅧", "🆇", "🅇"],
        "y": ["🅨", "🆈", "🅈"], "z": ["🅩", "🆉", "🅉"],
    }

    async def convert(self, prompt: str) -> str:
        result = []
        for c in prompt.lower():
            opts = self._MAP.get(c)
            result.append(random.choice(opts) if opts else c)
        return "".join(result)


class FlipConverter(BaseConverter):
    """Reverses the entire prompt string. e.g. 'hello me' → 'em olleh'"""

    async def convert(self, prompt: str) -> str:
        return prompt[::-1]


class InsertPunctuationConverter(BaseConverter):
    """Inserts punctuation randomly between or within words."""

    _DEFAULT_PUNCT = [",", ".", "!", "?", ":", ";", "-"]

    def __init__(self, word_swap_ratio: float = 0.2, between_words: bool = True) -> None:
        if not 0 < word_swap_ratio <= 1:
            raise ValueError("word_swap_ratio must be in (0, 1]")
        self._ratio = word_swap_ratio
        self._between_words = between_words

    async def convert(self, prompt: str) -> str:
        words = re.findall(r"\w+|\S+", prompt)
        if not words:
            return prompt
        num_insert = max(1, math.ceil(len(words) * self._ratio))
        positions = sorted(random.sample(range(len(words)), min(num_insert, len(words))))
        result = list(words)
        offset = 0
        for pos in positions:
            p = random.choice(self._DEFAULT_PUNCT)
            if self._between_words:
                result.insert(pos + offset + 1, p)
                offset += 1
            else:
                w = result[pos + offset]
                if len(w) > 1:
                    idx = random.randint(1, len(w) - 1)
                    result[pos + offset] = w[:idx] + p + w[idx:]
        return " ".join(result)


class LeetspeakConverter(BaseConverter):
    """Converts text to leetspeak (1337) substitutions."""

    _DEFAULT: Dict[str, List[str]] = {
        "a": ["4", "@", "/\\", "^", "/-\\"],
        "b": ["8", "6", "13", "|3", "/3"],
        "c": ["(", "[", "<", "{"],
        "e": ["3"],
        "g": ["9"],
        "i": ["1", "!"],
        "l": ["1", "|"],
        "o": ["0"],
        "s": ["5", "$"],
        "t": ["7"],
        "z": ["2"],
    }

    def __init__(self, deterministic: bool = False, custom_substitutions: Optional[dict] = None) -> None:
        self._subs = custom_substitutions if custom_substitutions else self._DEFAULT
        self._deterministic = deterministic

    async def convert(self, prompt: str) -> str:
        result = []
        for c in prompt:
            opts = self._subs.get(c.lower())
            if opts:
                result.append(opts[0] if self._deterministic else random.choice(opts))
            else:
                result.append(c)
        return "".join(result)


class MorseConverter(BaseConverter):
    """Converts text to Morse code (space separates chars, / separates words)."""

    _CODE: Dict[str, str] = {
        "a": ".-",   "b": "-...", "c": "-.-.", "d": "-..",  "e": ".",
        "f": "..-.", "g": "--.",  "h": "....", "i": "..",   "j": ".---",
        "k": "-.-",  "l": ".-..", "m": "--",   "n": "-.",   "o": "---",
        "p": ".--.", "q": "--.-", "r": ".-.",  "s": "...",  "t": "-",
        "u": "..-",  "v": "...-", "w": ".--",  "x": "-..-", "y": "-.--",
        "z": "--..",
        "0": "-----", "1": ".----", "2": "..---", "3": "...--",
        "4": "....-", "5": ".....", "6": "-....", "7": "--...",
        "8": "---..", "9": "----.",
        ".": ".-.-.-", ",": "--..--", "?": "..--..", "!": "-.-.--",
        " ": "/",
    }
    _ERROR = "........"

    def __init__(self, *, append_description: bool = False) -> None:
        self.append_description = append_description

    async def convert(self, prompt: str) -> str:
        encoded = " ".join(self._CODE.get(c.lower(), self._ERROR) for c in prompt)
        if self.append_description:
            encoded += (
                "\n\n(Morse code: dots/dashes, space separates chars, / separates words)"
            )
        return encoded


class NoiseConverter(BaseConverter):
    """Inserts random noise characters to evade signature-based detection filters."""

    _NOISE = list("!@#$%^&*~`|")

    def __init__(self, noise_ratio: float = 0.05) -> None:
        if not 0 < noise_ratio <= 1:
            raise ValueError("noise_ratio must be in (0, 1]")
        self._ratio = noise_ratio

    async def convert(self, prompt: str) -> str:
        result = list(prompt)
        num_insert = max(1, int(len(prompt) * self._ratio))
        for _ in range(num_insert):
            pos = random.randint(0, len(result))
            result.insert(pos, random.choice(self._NOISE))
        return "".join(result)


class ROT13Converter(BaseConverter):
    """ROT13 encoding."""

    async def convert(self, prompt: str) -> str:
        return codecs.encode(prompt, "rot13")


class RandomCapitalLettersConverter(BaseConverter):
    """Randomly capitalizes a given percentage of alphabetic characters."""

    def __init__(self, percentage: float = 100.0) -> None:
        if not 0 < percentage <= 100:
            raise ValueError("percentage must be in (0, 100]")
        self.percentage = percentage

    async def convert(self, prompt: str) -> str:
        result = []
        for c in prompt:
            if c.isalpha() and random.uniform(0, 100) <= self.percentage:
                result.append(c.upper() if random.random() < 0.5 else c.lower())
            else:
                result.append(c)
        return "".join(result)


class RepeatTokenConverter(BaseConverter):
    """Repeats a token N times and combines with the prompt.

    token_insert_mode: 'prepend' | 'append' | 'split' | 'repeat'
    Reference: https://dropbox.tech/machine-learning/bye-bye-bye-evolution-of-repeated-token-attacks-on-chatgpt-models
    """

    def __init__(
        self,
        *,
        token_to_repeat: str = "!",
        times_to_repeat: int = 20,
        token_insert_mode: str = "prepend",
    ) -> None:
        if token_insert_mode not in ("split", "prepend", "append", "repeat"):
            raise ValueError("token_insert_mode must be split/prepend/append/repeat")
        self.token = " " + token_to_repeat.strip()
        self.times = times_to_repeat
        self.mode = token_insert_mode

    async def convert(self, prompt: str) -> str:
        repeated = self.token * self.times
        if self.mode == "repeat":
            return repeated
        if self.mode == "prepend":
            return repeated + " " + prompt
        if self.mode == "append":
            return prompt + repeated
        m = re.search(r"[.?!]", prompt)
        if m:
            pos = m.end()
            return prompt[:pos] + repeated + " " + prompt[pos:]
        return repeated + " " + prompt


class SearchReplaceConverter(BaseConverter):
    """Replaces regex pattern matches with a given replacement string."""

    def __init__(self, pattern: str, replace: "str | list[str]", regex_flags: int = 0) -> None:
        self.pattern = pattern
        self.replace_list = [replace] if isinstance(replace, str) else replace
        self.flags = regex_flags

    async def convert(self, prompt: str) -> str:
        return re.sub(self.pattern, random.choice(self.replace_list), prompt, flags=self.flags)


class StringJoinConverter(BaseConverter):
    """Joins each character of the prompt with a separator. e.g. 'hi' → 'h-i'"""

    def __init__(self, *, join_value: str = "-") -> None:
        self.join_value = join_value

    async def convert(self, prompt: str) -> str:
        return self.join_value.join(prompt)


class SuffixAppendConverter(BaseConverter):
    """Appends a fixed suffix string to the prompt."""

    def __init__(self, *, suffix: str) -> None:
        if not suffix:
            raise ValueError("suffix must not be empty")
        self.suffix = suffix

    async def convert(self, prompt: str) -> str:
        return prompt + " " + self.suffix


class TextToHexConverter(BaseConverter):
    """Converts text to its uppercase hexadecimal UTF-8 byte representation."""

    async def convert(self, prompt: str) -> str:
        return prompt.encode("utf-8").hex().upper()


class UrlConverter(BaseConverter):
    """URL-encodes the prompt (percent-encoding)."""

    async def convert(self, prompt: str) -> str:
        return urllib.parse.quote(prompt)


class ZeroWidthConverter(BaseConverter):
    """Inserts zero-width spaces (U+200B) between every character."""

    _ZWS = "​"

    async def convert(self, prompt: str) -> str:
        return self._ZWS.join(prompt)


# ---------------------------------------------------------------------------
# Registry — maps class name → class for use by instantiate_converters
# ---------------------------------------------------------------------------
_REGISTRY: Dict[str, type] = {cls.__name__: cls for cls in [
    AnsiAttackConverter, AsciiSmugglerConverter, AtbashConverter,
    Base64Converter, BinaryConverter, CaesarConverter,
    CharSwapGenerator, CharacterSpaceConverter, ColloquialWordswapConverter,
    EmojiConverter, FlipConverter, InsertPunctuationConverter,
    LeetspeakConverter, MorseConverter, NoiseConverter,
    ROT13Converter, RandomCapitalLettersConverter, RepeatTokenConverter,
    SearchReplaceConverter, StringJoinConverter, SuffixAppendConverter,
    TextToHexConverter, UrlConverter, ZeroWidthConverter,
]}


def get_converter_class(name: str) -> type:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown native converter: {name!r}")
    return cls
