"""Manual Scan wizard.

Mirrors the CLI ``do_manual`` flow as a multi-step Textual wizard:

  1. ATLAS technique           (single-select dropdown)
  2. Attack methods            (multi-select, filtered by technique)
  3. Adversarial prompts       (multi-select from signatures + free entry)
  4. Jailbreak / response enc. (single-select; applied only to Single_* attacks)
  5. Prompt converters         (multi-select, optional)
  6. Review & start

The collected selections are expanded into a list of ``ExecutionJob`` and
handed to :class:`tui.screens.execution.ExecutionScreen` for sequential
execution.
"""

from __future__ import annotations

from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Button, ContentSwitcher, Footer, Header, Label, Select,
    SelectionList, Static, TextArea,
)

from converters.instantiate_converters import instantiate_converters
from utils import (
    apply_jailbreak_method, apply_response_converter_method,
    list_converters, list_jailbreak_templates, list_response_converters,
    load_atlas_catalog, load_dataset, load_jailbreak_template,
    load_prompt_techniques,
)

_NONE_JAILBREAK_VALUE = "__none__"
_NONE_RESPONSE_VALUE = ""
_NO_TECHNIQUE_VALUE = ""

_STEP_IDS = ["step-1", "step-2", "step-3", "step-4", "step-5", "step-6"]
_STEP_LABELS = ["Technique", "Attacks", "Prompts", "Jailbreak", "Converters", "Review"]


class ManualScanScreen(Screen):
    """Multi-step wizard for assembling a manual scan run."""

    BINDINGS = [Binding("escape", "go_back", "Back")]

    def __init__(self) -> None:
        super().__init__()
        catalog = load_atlas_catalog()
        self._techniques: dict = catalog["techniques"]
        self._tactics: dict = catalog["tactics"]

        # Language-independent catalogs.
        self._converters = list_converters()
        self._prompt_techniques: dict = load_prompt_techniques()
        # Language-dependent caches; populated in compose() when self.app is reachable.
        self._jailbreak_templates: list = []
        self._response_converters: list = []

        self._step_idx: int = 0

        # Selections collected across steps.
        self._sel_technique_id: str = ""
        self._sel_attacks: list[str] = []
        self._sel_prompts: list[str] = []
        self._sel_custom_prompts: list[str] = []
        self._sel_custom_technique: str = _NO_TECHNIQUE_VALUE
        self._sel_jailbreak_path: str = ""
        self._sel_response_value: str = _NONE_RESPONSE_VALUE
        self._sel_converters: list[str] = []

        # value -> prompt_technique mapping built from signatures.yaml when step 3 loads.
        self._prompt_technique_by_value: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    #  Compose                                                             #
    # ------------------------------------------------------------------ #

    def compose(self) -> ComposeResult:
        # Resolve the target language once at compose time so step-3 prompt labels,
        # step-4 jailbreak/response options share the same view.
        language = self.app.settings.get("target_language", "en")
        self._jailbreak_templates = list_jailbreak_templates(language=language)
        self._response_converters = list_response_converters(language=language)

        yield Header()
        yield Static(self._render_indicator(), id="step-indicator")

        with ContentSwitcher(initial=_STEP_IDS[0], id="wizard-body"):
            with Vertical(id="step-1"):
                yield Label("Step 1 / 6 — Select an ATLAS technique", classes="step-title")
                yield Select(
                    options=self._technique_options(),
                    allow_blank=False,
                    id="technique-select",
                )

            with Vertical(id="step-2"):
                yield Label("Step 2 / 6 — Select attack methods", classes="step-title")
                yield Label(
                    "Use Space to toggle. Multiple attacks may be selected; each is run "
                    "against every selected prompt.",
                    classes="field-label",
                )
                yield SelectionList(id="attacks-selection")

            with Vertical(id="step-3"):
                yield Label("Step 3 / 6 — Select adversarial prompts", classes="step-title")
                yield Label(
                    "Pick from the dataset and/or add custom prompts (one per line). "
                    "Each dataset prompt carries a prompt-crafting technique that biases "
                    "multi-turn attack generation.",
                    classes="field-label",
                )
                yield SelectionList(id="prompts-selection")
                yield Label("Custom prompts (optional, one per line):", classes="field-label")
                yield TextArea("", id="custom-prompts-input")
                yield Label(
                    "Prompt technique to apply to custom prompts (optional):",
                    classes="field-label",
                )
                yield Select(
                    options=self._prompt_technique_options(),
                    allow_blank=False,
                    value=_NO_TECHNIQUE_VALUE,
                    id="custom-technique-select",
                )

            with Vertical(id="step-4"):
                yield Label("Step 4 / 6 — Jailbreak / response encoding", classes="step-title")
                yield Label("", id="step-4-note", classes="field-label")
                yield Label("Jailbreak template:", classes="field-label")
                yield Select(
                    options=self._jailbreak_options(),
                    allow_blank=False,
                    value=_NONE_JAILBREAK_VALUE,
                    id="jailbreak-select",
                )
                yield Label("Response encoding:", classes="field-label")
                yield Select(
                    options=self._response_options(),
                    allow_blank=False,
                    value=_NONE_RESPONSE_VALUE,
                    id="response-select",
                )

            with Vertical(id="step-5"):
                yield Label("Step 5 / 6 — Prompt converters (optional)", classes="step-title")
                yield Label(
                    "Converters transform the attack prompt before it reaches the target. "
                    "Leave empty to send prompts unmodified.",
                    classes="field-label",
                )
                yield SelectionList(id="converters-selection")

            with Vertical(id="step-6"):
                yield Label("Step 6 / 6 — Review & start", classes="step-title")
                yield Static("", id="review-summary")

        with Horizontal(id="wizard-nav"):
            yield Button("Back", id="btn-back", disabled=True)
            yield Button("Next", id="btn-next", variant="primary")
            yield Button("Cancel", id="btn-cancel")
        yield Footer()

    # ------------------------------------------------------------------ #
    #  Mount                                                               #
    # ------------------------------------------------------------------ #

    def on_mount(self) -> None:
        # Pre-populate converter list (independent of any earlier selection).
        sel = self.query_one("#converters-selection", SelectionList)
        for c in self._converters:
            label = f"{c['name']}: {c['description']}"
            sel.add_option((Text(label), c["name"], False))

        # Default the technique select to the first option so step 2 has data.
        opts = self._technique_options()
        if opts:
            self.query_one("#technique-select", Select).value = opts[0][1]
            self._sel_technique_id = opts[0][1]

    # ------------------------------------------------------------------ #
    #  Option builders                                                     #
    # ------------------------------------------------------------------ #

    def _technique_options(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for tid, t in self._techniques.items():
            primary = t["tactics"][0]
            tactic_name = self._tactics.get(primary, {}).get("name", primary)
            label = f"[{tactic_name}] {tid}: {t['name']}"
            out.append((label, tid))
        return out

    def _jailbreak_options(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = [("(none) — no jailbreak template", _NONE_JAILBREAK_VALUE)]
        for j in self._jailbreak_templates:
            label = j.label
            if j.is_fallback:
                label += f" [{j.language_used}→fallback]"
            if j.description:
                label += f" — {j.description[:60]}"
            out.append((label, j.path))
        return out

    def _response_options(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for r in self._response_converters:
            label = f"{r['name']}: {r['value']}"
            if r.get("is_fallback"):
                label = f"[{r.get('language_used', 'en')}→fallback] " + label
            out.append((label, r["value"]))
        # Ensure a (none) entry exists even if the dataset is empty.
        if not any(v == _NONE_RESPONSE_VALUE for _, v in out):
            out.insert(0, ("(none) — no response encoding", _NONE_RESPONSE_VALUE))
        return out

    def _prompt_technique_options(self) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = [("(none) — no technique bias", _NO_TECHNIQUE_VALUE)]
        for key, entry in self._prompt_techniques.items():
            label = f"{key.replace('_', ' ')} — {entry.get('description', '')[:80]}"
            out.append((label, key))
        return out

    # ------------------------------------------------------------------ #
    #  Step indicator                                                      #
    # ------------------------------------------------------------------ #

    def _render_indicator(self) -> str:
        parts: list[str] = []
        for i, label in enumerate(_STEP_LABELS):
            mark = "●" if i == self._step_idx else "○"
            parts.append(f"{mark} {label}")
        return "   ".join(parts)

    def _refresh_indicator(self) -> None:
        self.query_one("#step-indicator", Static).update(self._render_indicator())

    # ------------------------------------------------------------------ #
    #  Navigation                                                          #
    # ------------------------------------------------------------------ #

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.app.pop_screen()
        elif event.button.id == "btn-back":
            self._go_back()
        elif event.button.id == "btn-next":
            self._go_next()

    def _go_back(self) -> None:
        if self._step_idx == 0:
            return
        self._step_idx -= 1
        self._switch_to(self._step_idx)

    def _go_next(self) -> None:
        # Validate / commit the current step before advancing.
        if not self._commit_current_step():
            return
        if self._step_idx == len(_STEP_IDS) - 1:
            self._start_run()
            return
        self._step_idx += 1
        self._switch_to(self._step_idx)

    def _switch_to(self, idx: int) -> None:
        self.query_one("#wizard-body", ContentSwitcher).current = _STEP_IDS[idx]
        self._refresh_indicator()
        self._enter_step(idx)

        back = self.query_one("#btn-back", Button)
        nxt = self.query_one("#btn-next", Button)
        back.disabled = idx == 0
        nxt.label = "Start scan" if idx == len(_STEP_IDS) - 1 else "Next"

    # ------------------------------------------------------------------ #
    #  Per-step entry / commit                                             #
    # ------------------------------------------------------------------ #

    def _enter_step(self, idx: int) -> None:
        """Refresh dynamic content when entering a step."""
        if idx == 1:
            self._populate_attacks()
        elif idx == 2:
            self._populate_prompts()
        elif idx == 3:
            self._refresh_step4_note()
        elif idx == 5:
            self._refresh_review()

    def _commit_current_step(self) -> bool:
        """Validate + commit selections for the active step.

        Returns False to block navigation when validation fails.
        """
        idx = self._step_idx
        if idx == 0:
            value = self.query_one("#technique-select", Select).value
            if not value or value is Select.BLANK:
                self.notify("Please select a technique.", severity="warning")
                return False
            if value != self._sel_technique_id:
                # Technique changed — reset downstream selections.
                self._sel_technique_id = str(value)
                self._sel_attacks = []
                self._sel_prompts = []
                self._sel_custom_prompts = []
            return True

        if idx == 1:
            selected = list(self.query_one("#attacks-selection", SelectionList).selected)
            if not selected:
                self.notify("Select at least one attack.", severity="warning")
                return False
            self._sel_attacks = selected
            return True

        if idx == 2:
            selected = list(self.query_one("#prompts-selection", SelectionList).selected)
            raw_custom = self.query_one("#custom-prompts-input", TextArea).text
            custom = [line.strip() for line in raw_custom.splitlines() if line.strip()]
            if not selected and not custom:
                self.notify(
                    "Select at least one prompt or add a custom one.",
                    severity="warning",
                )
                return False
            self._sel_prompts = selected
            self._sel_custom_prompts = custom
            self._sel_custom_technique = str(
                self.query_one("#custom-technique-select", Select).value
                or _NO_TECHNIQUE_VALUE
            )
            return True

        if idx == 3:
            self._sel_jailbreak_path = str(
                self.query_one("#jailbreak-select", Select).value or _NONE_JAILBREAK_VALUE
            )
            self._sel_response_value = str(
                self.query_one("#response-select", Select).value or _NONE_RESPONSE_VALUE
            )
            return True

        if idx == 4:
            self._sel_converters = list(
                self.query_one("#converters-selection", SelectionList).selected
            )
            return True

        return True

    # ------------------------------------------------------------------ #
    #  Dynamic population                                                  #
    # ------------------------------------------------------------------ #

    def _populate_attacks(self) -> None:
        sel = self.query_one("#attacks-selection", SelectionList)
        sel.clear_options()
        technique = self._techniques.get(self._sel_technique_id, {})
        for atk in technique.get("compatible_attacks", []):
            sel.add_option((Text(atk), atk, atk in self._sel_attacks))

    def _populate_prompts(self) -> None:
        sel = self.query_one("#prompts-selection", SelectionList)
        sel.clear_options()
        self._prompt_technique_by_value.clear()
        language = self.app.settings.get("target_language", "en")
        for entry in load_dataset("signatures.yaml", self._sel_technique_id, language=language):
            value = entry["value"]
            if value in self._prompt_technique_by_value:
                continue
            tech = entry.get("prompt_technique", "")
            self._prompt_technique_by_value[value] = tech
            fb_marker = f" [{entry['language_used']}→fallback]" if entry.get("is_fallback") else ""
            label = f"[{tech}]{fb_marker} {value}" if tech else f"{fb_marker} {value}".strip()
            sel.add_option((Text(label), value, value in self._sel_prompts))

    def _refresh_step4_note(self) -> None:
        has_single = any(a.startswith("Single_") for a in self._sel_attacks)
        note = self.query_one("#step-4-note", Label)
        jb = self.query_one("#jailbreak-select", Select)
        rs = self.query_one("#response-select", Select)
        if has_single:
            note.update("Applied to Single_* attack prompts only.")
            jb.disabled = False
            rs.disabled = False
        else:
            note.update("(Skipped — no Single_* attack selected. Will be ignored.)")
            jb.disabled = True
            rs.disabled = True

    def _refresh_review(self) -> None:
        prompt_count = len(self._sel_prompts) + len(self._sel_custom_prompts)
        attack_count = len(self._sel_attacks)
        total_runs = prompt_count * attack_count

        jb_label = self._jailbreak_label()
        re_label = self._response_label()
        conv_label = ", ".join(self._sel_converters) if self._sel_converters else "(none)"

        technique = self._techniques.get(self._sel_technique_id, {})
        primary = technique.get("tactics", ["?"])[0]
        tactic_name = self._tactics.get(primary, {}).get("name", primary)

        # Distribution of prompt-crafting techniques across selected prompts.
        tech_counts: dict[str, int] = {}
        for v in self._sel_prompts:
            key = self._prompt_technique_by_value.get(v, "") or "(none)"
            tech_counts[key] = tech_counts.get(key, 0) + 1
        if self._sel_custom_prompts:
            key = self._sel_custom_technique or "(none)"
            tech_counts[key] = tech_counts.get(key, 0) + len(self._sel_custom_prompts)
        tech_summary = ", ".join(
            f"{k}×{v}" for k, v in sorted(tech_counts.items(), key=lambda kv: -kv[1])
        ) or "(none)"

        summary = (
            f"Technique  : [{tactic_name}] {self._sel_technique_id} "
            f"— {technique.get('name', '')}\n"
            f"Attacks    : {', '.join(self._sel_attacks) or '(none)'}\n"
            f"Prompts    : {prompt_count} "
            f"({len(self._sel_prompts)} dataset, {len(self._sel_custom_prompts)} custom)\n"
            f"Prompt tech: {tech_summary}\n"
            f"Jailbreak  : {jb_label}\n"
            f"Resp. enc. : {re_label}\n"
            f"Converters : {conv_label}\n"
            f"Total runs : {total_runs} (attacks × prompts)"
        )
        self.query_one("#review-summary", Static).update(summary)

    def _jailbreak_label(self) -> str:
        if not self._sel_jailbreak_path or self._sel_jailbreak_path == _NONE_JAILBREAK_VALUE:
            return "(none)"
        for t in self._jailbreak_templates:
            if t.path == self._sel_jailbreak_path:
                return t.label
        return self._sel_jailbreak_path

    def _response_label(self) -> str:
        if not self._sel_response_value:
            return "(none)"
        for r in self._response_converters:
            if r["value"] == self._sel_response_value:
                return r["name"]
        return self._sel_response_value[:60]

    # ------------------------------------------------------------------ #
    #  Build jobs and start                                                #
    # ------------------------------------------------------------------ #

    def _start_run(self) -> None:
        if not self.app.settings_ready():
            self.notify(
                "Settings incomplete — check API endpoint, LLM names, and API keys.",
                severity="error",
            )
            return

        raw_prompts: list[str] = list(self._sel_prompts) + list(self._sel_custom_prompts)
        if not raw_prompts:
            self.notify("No prompts selected.", severity="warning")
            return

        # Per-prompt prompt-crafting technique (parallel list to raw_prompts).
        prompt_techs: list[str] = [
            self._prompt_technique_by_value.get(p, "") for p in self._sel_prompts
        ] + [self._sel_custom_technique] * len(self._sel_custom_prompts)

        language = self.app.settings.get("target_language", "en")

        # Apply jailbreak / response encoding only to Single_* attacks.
        jailbreak_value: str | None = None
        if self._sel_jailbreak_path and self._sel_jailbreak_path != _NONE_JAILBREAK_VALUE:
            try:
                jailbreak_value = load_jailbreak_template(
                    self._sel_jailbreak_path, language=language,
                ).value
            except Exception as exc:
                self.notify(
                    f"Failed to load jailbreak template: {exc}",
                    severity="error",
                )
                return

        response_value = self._sel_response_value or None

        single_objectives = list(raw_prompts)
        if jailbreak_value:
            single_objectives = apply_jailbreak_method(single_objectives, jailbreak_value)
        if response_value:
            single_objectives = apply_response_converter_method(single_objectives, response_value)

        # Build the job list — multi-turn attacks always use raw prompts; Single_* uses
        # the jailbreak/response-encoding-wrapped variant. The prompt_technique is
        # carried through to bias multi-turn adv-LLM strategy in the attack class.
        from tui.screens.execution import ExecutionJob, ExecutionScreen

        jobs: list[ExecutionJob] = []
        for attack_id in self._sel_attacks:
            objectives = single_objectives if attack_id.startswith("Single_") else raw_prompts
            for objective, ptech in zip(objectives, prompt_techs):
                jobs.append(ExecutionJob(
                    attack_id=attack_id,
                    objective=objective,
                    technique_id=self._sel_technique_id,
                    prompt_technique=ptech,
                ))

        if not jobs:
            self.notify("No jobs to run.", severity="warning")
            return

        try:
            converter_instances = instantiate_converters(self._sel_converters)
        except Exception as exc:
            self.notify(f"Failed to load converters: {exc}", severity="error")
            return

        try:
            ctx = self.app.build_context(converter_instances=converter_instances)
        except FileNotFoundError as exc:
            self.notify(
                f"Browser config file not found:\n{exc.filename or exc}",
                title="Cannot start scan",
                severity="error",
                timeout=8,
            )
            return
        except Exception as exc:
            self.notify(
                f"Failed to initialize target: {exc}",
                title="Cannot start scan",
                severity="error",
                timeout=8,
            )
            return

        self.app.push_screen(ExecutionScreen(ctx=ctx, jobs=jobs))

    def action_go_back(self) -> None:
        self.app.pop_screen()
