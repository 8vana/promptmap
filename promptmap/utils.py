import pathlib
from dataclasses import dataclass
from typing import List, Tuple, Union

import yaml

# Package root — used to resolve bundled dataset / config paths regardless of cwd.
PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent

JAILBREAK_PLACEHOLDER = "{{ prompt }}"

# Languages supported across signatures / jailbreak templates / response_encode.
# Adding a new language: extend SUPPORTED_LANGUAGES + LANGUAGE_DISPLAY_NAMES,
# add translations to the YAML files, then add it to the TUI Settings dropdown.
BASE_LANGUAGE = "en"
SUPPORTED_LANGUAGES: Tuple[str, ...] = ("en", "ja")
LANGUAGE_DISPLAY_NAMES = {"en": "English", "ja": "日本語"}


@dataclass
class JailbreakTemplate:
    """Parsed and validated jailbreak template (SeedPrompt-compatible YAML)."""
    name: str
    value: str
    path: str
    description: str = ""
    source: str = ""
    label: str = ""           # e.g. "[builtin] DAN 11" — for UI display
    language_used: str = BASE_LANGUAGE  # actual language whose value was returned
    is_fallback: bool = False           # True if requested language was missing


def load_mapping(path: Union[str, pathlib.Path]) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


def load_atlas_catalog(path: Union[str, pathlib.Path, None] = None) -> dict:
    if path is None:
        path = PACKAGE_ROOT / "config" / "atlas_catalog.yaml"
    with open(path, "r") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------------------
# Multi-language helpers
# ------------------------------------------------------------------
def _normalize_languages(entry: dict, legacy_field: str = "value") -> dict:
    """Return ``{language_code: text}`` from an entry regardless of schema.

    Supports two shapes:
      * New: ``languages: {en: "...", ja: "..."}``
      * Legacy: ``<legacy_field>: "..."`` (treated as English-only)

    Returns an empty dict when neither shape produces a usable string.
    """
    langs = entry.get("languages")
    if isinstance(langs, dict):
        return {k: v for k, v in langs.items() if isinstance(v, str) and v}
    legacy = entry.get(legacy_field)
    if isinstance(legacy, str) and legacy:
        return {BASE_LANGUAGE: legacy}
    return {}


def _resolve_language(langs: dict, language: str) -> Tuple[str, str]:
    """Pick the best translation for ``language`` from a {lang: text} map.

    Order of preference: requested → BASE_LANGUAGE → first available.
    Returns ``(text, language_used)``; ``("", "")`` if the map is empty.
    """
    if language and language in langs:
        return langs[language], language
    if BASE_LANGUAGE in langs:
        return langs[BASE_LANGUAGE], BASE_LANGUAGE
    if langs:
        any_lang = next(iter(langs))
        return langs[any_lang], any_lang
    return "", ""


def _prompt_entry_to_langs(prompt_entry: dict) -> dict:
    """Extract ``{lang_code: text}`` from a flat prompt entry ``{en: "...", ja: "..."}``.

    Only keys matching ``SUPPORTED_LANGUAGES`` with non-empty string values are
    returned, so future schema extensions (e.g. per-prompt notes) won't be
    misread as translations.
    """
    return {
        k: v for k, v in prompt_entry.items()
        if k in SUPPORTED_LANGUAGES and isinstance(v, str) and v
    }


def load_dataset(
    dataset_filename: str,
    atlas_technique_id: str,
    language: str = BASE_LANGUAGE,
) -> List[dict]:
    """Load adversarial prompts for an ATLAS technique, resolved to ``language``.

    Reads the nested structure under the ``signatures:`` root key:

        signatures:
          - atlas_technique: <id>
            prompt_techniques:
              <Prompt_Technique_Name>:
                prompts:
                  - en: "..."
                    ja: "..."

    Each group corresponds to exactly one ATLAS technique. Prompts that apply
    to multiple ATLAS techniques are duplicated across groups intentionally
    to keep the data flat and the loader trivial.

    Returns ``[{value, prompt_technique, language_used, is_fallback}]``.
    Entries with no usable translation are silently dropped.
    """
    path = PACKAGE_ROOT / "datasets" / dataset_filename
    with open(path, "r") as f:
        data = yaml.safe_load(f) or {}

    out: List[dict] = []
    for group in data.get("signatures", []) or []:
        if group.get("atlas_technique") != atlas_technique_id:
            continue
        for tech_name, tech_body in (group.get("prompt_techniques") or {}).items():
            if not isinstance(tech_body, dict):
                continue
            for prompt_entry in tech_body.get("prompts") or []:
                if not isinstance(prompt_entry, dict):
                    continue
                langs = _prompt_entry_to_langs(prompt_entry)
                value, used = _resolve_language(langs, language)
                if not value:
                    continue
                out.append({
                    "value": value,
                    "prompt_technique": tech_name,
                    "language_used": used,
                    "is_fallback": used != language,
                })
    return out


def apply_jailbreak_method(prompts, jailbreak_template=None):
    if jailbreak_template is None:
        return prompts
    return [jailbreak_template.replace(JAILBREAK_PLACEHOLDER, p) for p in prompts]


def apply_response_converter_method(prompts, response_converter=None):
    if response_converter is None:
        return prompts
    return [f"{p}\n\n{response_converter}" for p in prompts]


def list_converters() -> List[dict]:
    """Return all available prompt converters as [{'name', 'description'}]."""
    loaded_yaml = load_mapping(PACKAGE_ROOT / "converters" / "converters.yaml")
    return list(loaded_yaml["converters"])


def load_jailbreak_template(
    path: str | pathlib.Path,
    language: str = BASE_LANGUAGE,
) -> JailbreakTemplate:
    """Load and validate a jailbreak template YAML, resolved to ``language``.

    Validates that a usable ``value`` exists for the resolved language and that it
    contains the ``{{ prompt }}`` placeholder. Falls back to ``BASE_LANGUAGE`` if
    the requested language has no translation.
    """
    p = pathlib.Path(path)
    with open(p, "r") as f:
        data = yaml.safe_load(f) or {}

    langs = _normalize_languages(data)
    if not langs:
        raise ValueError(f"{p.name}: 'value' field is missing, empty, or not a string")
    value, used = _resolve_language(langs, language)
    if not value:
        raise ValueError(f"{p.name}: no usable jailbreak value found")
    if JAILBREAK_PLACEHOLDER not in value:
        raise ValueError(
            f"{p.name} ({used}): 'value' must contain the placeholder "
            f"{JAILBREAK_PLACEHOLDER!r}; without it the user's objective is silently dropped"
        )

    return JailbreakTemplate(
        name=str(data.get("name") or p.stem),
        value=value,
        path=str(p),
        description=str(data.get("description") or ""),
        source=str(data.get("source") or ""),
        language_used=used,
        is_fallback=used != language,
    )


def list_jailbreak_templates(language: str = BASE_LANGUAGE) -> List[JailbreakTemplate]:
    """Discover available jailbreak templates with parsed metadata for ``language``.

    Both the allowed builtin templates (from ``datasets/jailbreak_config.yaml``)
    and any user-defined files under ``datasets/custom_jailbreaks/`` are included.
    Files that fail validation are silently skipped here — the startup
    integrity check (``validate_dataset_references``) surfaces those errors so
    the wizard remains usable.
    """
    builtin_dir = _builtin_jailbreak_dir()
    custom_dir = PACKAGE_ROOT / "datasets" / "custom_jailbreaks"

    allowed = load_mapping(PACKAGE_ROOT / "datasets" / "jailbreak_config.yaml")
    out: List[JailbreakTemplate] = []
    for fn in allowed.get("builtin_templates", []):
        p = builtin_dir / fn
        if not p.is_file():
            continue
        try:
            tmpl = load_jailbreak_template(p, language=language)
        except (ValueError, OSError):
            continue
        tmpl.label = f"[builtin] {tmpl.name}"
        out.append(tmpl)
    if custom_dir.exists():
        for p in sorted(custom_dir.glob("*.yaml")):
            try:
                tmpl = load_jailbreak_template(p, language=language)
            except (ValueError, OSError):
                continue
            tmpl.label = f"[custom] {tmpl.name}"
            out.append(tmpl)
    return out


def list_response_converters(language: str = BASE_LANGUAGE) -> List[dict]:
    """Return response-encode prompts as [{'name', 'value', 'language_used', 'is_fallback'}]."""
    loaded_yaml = load_mapping(PACKAGE_ROOT / "datasets" / "response_encode.yaml")
    out: List[dict] = []
    for entry in loaded_yaml.get("prompts", []) or []:
        langs = _normalize_languages(entry)
        value, used = _resolve_language(langs, language)
        if not value:
            continue
        out.append({
            "name": entry.get("name", ""),
            "value": value,
            "language_used": used,
            "is_fallback": used != language,
        })
    return out


def load_prompt_techniques(path: Union[str, pathlib.Path, None] = None) -> dict:
    """Return ``{technique_key: {description: str}}`` from prompt_techniques.yaml."""
    if path is None:
        path = PACKAGE_ROOT / "config" / "prompt_techniques.yaml"
    return load_mapping(path).get("prompt_techniques", {})


def build_technique_guidance(technique_key: str | None) -> str:
    """Format an adv-LLM system-prompt suffix biasing toward a prompt-crafting technique.

    Returns an empty string when ``technique_key`` is missing, blank, or unknown,
    so callers can safely concatenate the result without a conditional.
    """
    if not technique_key:
        return ""
    catalog = load_prompt_techniques()
    entry = catalog.get(technique_key)
    if not entry:
        return ""
    desc = entry.get("description", "")
    pretty = technique_key.replace("_", " ")
    return (
        "\n\nPreferred adversarial technique to use throughout this engagement:\n"
        f"  - Name: {pretty}\n"
        f"  - Description: {desc}\n"
        "Bias your generated prompts toward this technique while still varying details "
        "and adapting to refusals."
    )


def build_language_directive(language: str | None) -> str:
    """Format an adv-LLM system-prompt suffix biasing output to a target language.

    Returns an empty string for the base language or unknown codes, so callers
    can safely concatenate the result without a conditional. Use this when the
    target system speaks a non-English language: capable LLMs (GPT-4o, Claude,
    Gemini) follow English meta-instructions but produce attack prompts in the
    requested language when explicitly told to.
    """
    if not language or language == BASE_LANGUAGE:
        return ""
    if language not in SUPPORTED_LANGUAGES:
        return ""
    name = LANGUAGE_DISPLAY_NAMES.get(language, language)
    return (
        f"\n\nIMPORTANT: The target system communicates in {name}. Generate every "
        f"adversarial prompt and conversational message in {name}. Native-language "
        "phrasing is far more effective than English against a non-English target."
    )


# Attack class names registered in tui/app.py:build_context. Kept here so the
# integrity check below can flag stale entries in atlas_catalog.yaml without
# importing the TUI module.
_REGISTERED_ATTACKS = {
    "Single_PI_Attack",
    "Multi_Crescendo_Attack",
    "Multi_PAIR_Attack",
    "Multi_TAP_Attack",
    "Multi_Chunked_Request_Attack",
}


def _validate_languages_block(blk_or_legacy_value, where: str, require_placeholder: bool = False) -> List[str]:
    """Validate a ``languages:`` map (or legacy ``value:`` field).

    ``blk_or_legacy_value`` is the entry dict — we read both ``languages`` and the
    legacy ``value`` field to support both schemas.
    """
    errs: List[str] = []
    langs = _normalize_languages(blk_or_legacy_value)
    if not langs:
        errs.append(f"{where}: no usable text (missing 'languages' map or legacy 'value' field)")
        return errs
    if BASE_LANGUAGE not in langs:
        errs.append(f"{where}: missing required base language '{BASE_LANGUAGE}'")
    for lang, text in langs.items():
        if lang not in SUPPORTED_LANGUAGES:
            errs.append(
                f"{where}: unsupported language code '{lang}' "
                f"(allowed: {sorted(SUPPORTED_LANGUAGES)})"
            )
        if require_placeholder and JAILBREAK_PLACEHOLDER not in text:
            errs.append(
                f"{where} ({lang}): missing placeholder {JAILBREAK_PLACEHOLDER!r} — "
                "user objective would be silently dropped"
            )
    return errs


def validate_dataset_references() -> List[str]:
    """Cross-check IDs/keys referenced across config/ and datasets/.

    Returns a list of human-readable error strings (empty list = all good).
    The startup path uses this to surface typos that would otherwise cause
    silent fail (filtered-out prompts, no-op technique guidance, etc.).
    """
    errors: List[str] = []

    try:
        catalog = load_atlas_catalog()
    except Exception as e:
        return [f"config/atlas_catalog.yaml: failed to load ({e})"]

    valid_atlas_ids = set((catalog.get("techniques") or {}).keys())
    valid_tactic_ids = set((catalog.get("tactics") or {}).keys())

    try:
        techniques = load_prompt_techniques()
    except Exception as e:
        errors.append(f"config/prompt_techniques.yaml: failed to load ({e})")
        techniques = {}
    valid_tech_keys = set(techniques.keys())

    # 1) atlas_catalog: each technique's tactics + compatible_attacks must be known.
    for tid, t in (catalog.get("techniques") or {}).items():
        for tac in t.get("tactics", []) or []:
            if tac not in valid_tactic_ids:
                errors.append(
                    f"atlas_catalog.yaml: technique '{tid}' references unknown tactic '{tac}'"
                )
        for atk in t.get("compatible_attacks", []) or []:
            if atk not in _REGISTERED_ATTACKS:
                errors.append(
                    f"atlas_catalog.yaml: technique '{tid}' references unknown "
                    f"compatible_attack '{atk}' (not registered in tui/app.py)"
                )

    # 2) signatures: nested structure
    #    signatures:
    #      - atlas_technique: <id>
    #        prompt_techniques:
    #          <Technique_Name>:
    #            prompts:
    #              - en: "..."
    #                ja: "..."
    sig_path = PACKAGE_ROOT / "datasets" / "signatures.yaml"
    try:
        with open(sig_path) as f:
            sig_data = yaml.safe_load(f) or {}
    except Exception as e:
        errors.append(f"datasets/signatures.yaml: failed to load ({e})")
        sig_data = {}
    for gi, group in enumerate(sig_data.get("signatures") or [], start=1):
        group_where = f"signatures.yaml group #{gi}"
        atlas_id = group.get("atlas_technique")
        if not atlas_id:
            errors.append(f"{group_where}: atlas_technique is empty")
        elif not isinstance(atlas_id, str):
            errors.append(
                f"{group_where}: atlas_technique must be a single string "
                f"(got {type(atlas_id).__name__})"
            )
        elif atlas_id not in valid_atlas_ids:
            errors.append(
                f"{group_where}: unknown atlas_technique '{atlas_id}' "
                "(not in atlas_catalog.yaml)"
            )

        pt_map = group.get("prompt_techniques")
        if pt_map is None:
            errors.append(f"{group_where}: missing 'prompt_techniques' field")
            continue
        if not isinstance(pt_map, dict):
            errors.append(
                f"{group_where}: 'prompt_techniques' must be a mapping "
                f"(got {type(pt_map).__name__})"
            )
            continue
        if not pt_map:
            errors.append(f"{group_where}: 'prompt_techniques' is empty")

        for tech_name, tech_body in pt_map.items():
            tech_where = f"{group_where} → '{tech_name}'"
            if tech_name not in valid_tech_keys:
                errors.append(
                    f"{tech_where}: unknown prompt_technique "
                    "(not in prompt_techniques.yaml)"
                )
            if not isinstance(tech_body, dict):
                errors.append(
                    f"{tech_where}: technique body must be a mapping with a 'prompts' field"
                )
                continue
            prompt_list = tech_body.get("prompts") or []
            if not prompt_list:
                errors.append(f"{tech_where}: 'prompts' is empty")
            for pi, prompt_entry in enumerate(prompt_list, start=1):
                if not isinstance(prompt_entry, dict):
                    errors.append(
                        f"{tech_where} prompt #{pi}: must be a mapping with language keys "
                        "(e.g. {en: ..., ja: ...})"
                    )
                    continue
                langs = _prompt_entry_to_langs(prompt_entry)
                preview = next(iter(langs.values()), "")[:60].replace("\n", " ")
                prompt_where = f"{tech_where} prompt #{pi} ('{preview}…')"
                # Detect unknown keys at the prompt level so typos like `english:` surface.
                unknown_keys = [k for k in prompt_entry if k not in SUPPORTED_LANGUAGES]
                for bad in unknown_keys:
                    errors.append(
                        f"{prompt_where}: unknown key '{bad}' "
                        f"(allowed language codes: {sorted(SUPPORTED_LANGUAGES)})"
                    )
                if not langs:
                    errors.append(f"{prompt_where}: no usable text in language keys")
                    continue
                if BASE_LANGUAGE not in langs:
                    errors.append(
                        f"{prompt_where}: missing required base language '{BASE_LANGUAGE}'"
                    )

    # 3) response_encode: each entry's languages must be known.
    try:
        re_data = load_mapping(PACKAGE_ROOT / "datasets" / "response_encode.yaml") or {}
    except Exception as e:
        errors.append(f"datasets/response_encode.yaml: failed to load ({e})")
        re_data = {}
    for i, entry in enumerate(re_data.get("prompts") or [], start=1):
        where = f"response_encode.yaml entry #{i} ('{entry.get('name', '')[:40]}')"
        errors.extend(_validate_languages_block(entry, where))

    # 4) jailbreak templates: must have a value containing the {{ prompt }} placeholder
    #    for every translation present.
    builtin_dir = _builtin_jailbreak_dir()
    custom_dir = PACKAGE_ROOT / "datasets" / "custom_jailbreaks"
    try:
        allowed = load_mapping(PACKAGE_ROOT / "datasets" / "jailbreak_config.yaml") or {}
    except Exception as e:
        errors.append(f"datasets/jailbreak_config.yaml: failed to load ({e})")
        allowed = {}
    for fn in allowed.get("builtin_templates") or []:
        p = builtin_dir / fn
        if not p.is_file():
            errors.append(
                f"jailbreak_config.yaml lists '{fn}' but datasets/builtin_jailbreaks/{fn} does not exist"
            )
            continue
        errors.extend(_validate_jailbreak_yaml(p, f"datasets/builtin_jailbreaks/{fn}"))
    if custom_dir.exists():
        for p in sorted(custom_dir.glob("*.yaml")):
            errors.extend(_validate_jailbreak_yaml(p, f"datasets/custom_jailbreaks/{p.name}"))

    return errors


def _validate_jailbreak_yaml(path: pathlib.Path, where: str) -> List[str]:
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except Exception as e:
        return [f"{where}: failed to load ({e})"]
    return _validate_languages_block(data, where, require_placeholder=True)


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------
def _builtin_jailbreak_dir() -> pathlib.Path:
    return PACKAGE_ROOT / "datasets" / "builtin_jailbreaks"
