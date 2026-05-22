# PromptMap Design: Forge Strengthening

## Status

Proposed next-step design after Phase C auditor MVP.

## Why This Exists

Current `forge` is working as a Phase B coder MVP, but the auditor output shows
its main weakness clearly:

- generated modules are PromptMap-compatible
- generated modules are runnable
- generated modules keep plan metadata explicit
- generated modules still rely on a **generic baseline flow**

This is good enough for a coder MVP, but not good enough for paper-faithful
attack onboarding.

The next design goal is not "full automatic attack implementation."
The goal is:

1. produce drafts that implement more plan steps directly
2. reduce generic baseline behavior
3. make coder output easier for `audit` to verify
4. preserve explicit uncertainty instead of hiding it

## Problem Statement

The current `forge` has three structural limitations.

### 1. Runtime Logic Is Too Generic

The generated `attack_module.py` mostly does this:

- merge params
- build a generic prompt
- send once or in a shallow loop
- score the response

This ignores most paper-specific attack structure.

### 2. Plan Steps Are Stored, Not Executed

`PLAN_STEPS` are preserved in metadata, but most steps do not become dedicated
code paths.

This causes `audit` to label many steps as:

- `missing`
- `partial`

even when the plan itself is good.

### 3. Coder Output Is Hard To Differentiate

Right now, many papers would generate roughly the same runtime draft:

- single-turn paper -> baseline direct prompt
- multi-turn paper -> baseline iterative loop

That reduces the value of the forge stage.

## Design Goals

- Move `forge` from "metadata-aware scaffold" to "plan-structured draft."
- Keep `BaseAttack` and `AttackContext` unchanged.
- Keep generated code runnable and conservative.
- Preserve `supports_benchmark: false`.
- Give `audit` richer implementation signals than string presence alone.
- Allow future LLM-assisted coder upgrades without breaking heuristic mode.

## Non-Goals

- Do not attempt paper-fidelity = 100%.
- Do not auto-promote generated code into `promptmap/attacks/`.
- Do not silently copy official repository implementations.
- Do not require LLM usage in the strengthened forge baseline.

## Core Idea

Strengthened `forge` should not generate one generic baseline.

It should generate one of a small number of **execution skeleton families**
derived from the implementation plan:

- `single_turn_splice`
- `single_turn_template`
- `dataset_rank_then_attack`
- `multi_turn_refinement`
- `autonomous_loop`

The purpose is not to perfectly implement the paper.
The purpose is to pick a draft structure that is **closer to the plan shape**
than the current baseline.

## Proposed Forge Architecture

```text
implementation_plan.json
        |
        v
Forge Classifier
  - infer execution skeleton
  - infer parameter groups
  - infer prompt assets
        |
        v
Draft Builder
  - choose code template
  - fill code sections from plan steps
  - emit explicit TODOs for unresolved logic
        |
        v
Artifact Emitter
  - attack_module.py
  - attack_catalog.yaml
  - generation_notes.md
  - benchmark_notes.md
  - review_checklist.md
```

## Strengthening Strategy

### 1. Add Execution Skeleton Classification

Before rendering code, `forge` should classify the plan into a more specific
runtime pattern.

Example rules:

- if plan mentions ranking + instruction selection + splicing:
  use `dataset_rank_then_attack`
- if plan is `single_turn` and includes template fragments:
  use `single_turn_template`
- if plan is `multi_turn` and includes retries or refinement:
  use `multi_turn_refinement`
- if family is `autonomous`:
  use `autonomous_loop`

This classification should be recorded in:

- `manifest.json`
- `generation_notes.md`
- `AttackResult.metadata`

Suggested manifest addition:

```json
{
  "forge_phase_b": {
    "forge_backend_used": "heuristic",
    "execution_skeleton": "dataset_rank_then_attack"
  }
}
```

### 2. Generate Plan-Shaped Helper Methods

Instead of a single generic `run`, generate helper methods derived from the
plan step families.

For example, a RADIAL-like draft should generate methods such as:

- `_collect_candidate_instructions(...)`
- `_calculate_response_tendencies(...)`
- `_rank_candidate_instructions(...)`
- `_filter_text_manipulation_instructions(...)`
- `_build_attack_prompt(...)`

Important rule:

- these methods may still contain TODOs
- but each method should correspond to a named plan step

This improves:

- readability
- local refinement
- auditor precision

### 3. Separate Preparation Phase From Attack Phase

Many papers are not "just prompt once."
They have an offline or precomputation phase.

Strengthened `forge` should explicitly model:

- preparation
- execution
- evaluation

Suggested structure:

```python
async def run(...):
    assets = await self._prepare_attack_assets(...)
    prompt = self._build_attack_prompt(...)
    response = await self._execute_attack(...)
    return self._finalize_result(...)
```

This makes papers like RADIAL easier to represent even if they stay partial.

### 4. Materialize Prompt Assets

If the plan includes `prompt_fragments`, `affirmation_response_example`,
`rejection_response_example`, or prompt templates, `forge` should materialize
them as named constants instead of leaving them only in metadata.

Example:

```python
AFFIRMATION_RESPONSE_EXAMPLES = [
    "Sure, here's the information.",
]
```

Benefits:

- clearer code
- better audit coverage
- easier manual completion

### 5. Emit TODOs At The Right Granularity

Current TODO behavior is too coarse.

Strengthened `forge` should emit TODOs tied to individual unresolved steps:

- `TODO(radial): implement probability extraction from target logits`
- `TODO(radial): load Alpaca-derived instruction candidates`
- `TODO(radial): implement ranking formula from paper:formula:3_2`

Every TODO should ideally include:

- attack id
- missing step id
- evidence ref or ambiguity reason

### 6. Add Generation Notes

Introduce a new artifact:

- `generation_notes.md`

This should explain:

- chosen execution skeleton
- which plan steps were mapped to code methods
- which plan steps were emitted as TODO-only
- which defaults were copied from plan
- which ambiguities were intentionally preserved

This helps human review and gives `audit` more explicit inputs later.

## Proposed Phase B.5 Output Model

After forge strengthening, staging should additionally contain:

- `generation_notes.md`

And `attack_module.py` should include:

- helper methods aligned with plan steps
- named prompt asset constants
- plan-linked TODOs
- explicit `metadata["forge_status"]`
- explicit `metadata["execution_skeleton"]`

## Execution Skeletons

### A. `single_turn_template`

Use when:

- family is `single_turn`
- paper mostly defines a framing/template attack

Shape:

- constants for templates/fragments
- `_build_attack_prompt`
- single send
- score

### B. `single_turn_splice`

Use when:

- family is `single_turn`
- plan references instruction splicing, prefix/suffix composition, or prompt
  wrapping

Shape:

- `_build_prefix_segments`
- `_build_suffix_segments`
- `_build_attack_prompt`
- single send
- score

### C. `dataset_rank_then_attack`

Use when:

- plan references candidate collection, scoring, ranking, selection, and final
  prompt construction

Shape:

- `_collect_candidate_inputs`
- `_score_candidates`
- `_select_attack_assets`
- `_build_attack_prompt`
- `_execute_attack`

This is the preferred RADIAL skeleton.

### D. `multi_turn_refinement`

Use when:

- family is `multi_turn`
- plan includes retries, rephrasing, adaptive turns, or maintained state

Shape:

- `_build_initial_prompt`
- `_analyze_response`
- `_refine_prompt`
- loop until stopping rule or max iterations

### E. `autonomous_loop`

Use when:

- family is `autonomous`

Shape:

- `_select_action`
- `_execute_action`
- `_score_progress`
- stop when satisfied

## Plan-to-Code Mapping Rules

The strengthened forge should build an internal mapping table:

```json
{
  "construct_responses": {
    "mapping_type": "constant_asset",
    "target_symbol": "AFFIRMATION_RESPONSE_EXAMPLES"
  },
  "calculate_probabilities": {
    "mapping_type": "helper_method",
    "target_symbol": "_calculate_response_tendencies",
    "todo_only": true
  }
}
```

This mapping should drive:

- generated code
- `generation_notes.md`
- future audit improvements

## Heuristic Forge v2 Rules

For the non-LLM strengthened forge, start with deterministic rules based on
plan content.

### Detection Signals

Use:

- `family`
- algorithm step ids
- algorithm step titles
- prompt fragments
- default params
- ambiguities

### Example Heuristic

If all are true:

- `family == single_turn`
- a step contains `rank`
- a step contains `select`
- a step contains `splice`

Then:

- choose `dataset_rank_then_attack`
- emit methods for collection / scoring / selection / prompt assembly
- mark missing formulas with TODOs

## LLM-Assisted Forge vNext

After the strengthened heuristic coder, add optional LLM assistance.

Recommended modes:

- `--forge-backend heuristic`
- `--forge-backend llm`
- `--forge-backend auto`

LLM-assisted forge should still be constrained:

- output code only through a structured coder response
- preserve plan step mapping
- do not mark `supports_benchmark: true`
- do not remove TODOs unless evidence supports the implementation

## Audit Integration Changes

Strengthened forge should make audit more precise.

The auditor can improve if it sees:

- helper method names tied to step ids
- `generation_notes.md`
- `execution_skeleton`
- step-to-symbol mapping

Recommended audit upgrade later:

- if step mapped to helper method and helper has body + emits runtime path:
  classify as `implemented`
- if step mapped to helper method but helper is TODO-only:
  classify as `partial`
- if no mapped symbol exists:
  classify as `missing`

## Proposed Artifact Additions

### `generation_notes.md`

Suggested contents:

- chosen execution skeleton
- step-to-code mapping table
- TODO-only steps
- preserved ambiguities
- benchmark recommendation note

### `manifest.json`

Extend `forge_phase_b`:

```json
{
  "forge_phase_b": {
    "forge_backend_used": "heuristic",
    "execution_skeleton": "dataset_rank_then_attack",
    "generation_notes_path": "generation_notes.md"
  }
}
```

## Incremental Implementation Plan

### Step 1

Add execution skeleton classification to `forger.py`.

### Step 2

Add a second forge template family:

- current generic draft remains fallback
- new specialized template for `dataset_rank_then_attack`

### Step 3

Emit `generation_notes.md`.

### Step 4

Encode step-to-symbol mapping in generated metadata.

### Step 5

Update `audit` to use:

- execution skeleton
- step mapping
- TODO markers

## Success Criteria

The forge strengthening effort is successful if:

- `audit` reports fewer false `missing` steps for structurally represented drafts
- generated drafts differ meaningfully across attack families
- developers can refine generated drafts faster than the current baseline
- generated code remains conservative and reviewable

## Recommendation

Do not jump directly to LLM-assisted forge v2.

The best next move is:

1. strengthen heuristic forge first
2. emit plan-shaped helper methods
3. emit `generation_notes.md`
4. upgrade audit to consume the richer structure
5. only then add optional LLM-backed forge

This keeps the workflow stable, testable, and aligned with PromptMap's current
review-first philosophy.
