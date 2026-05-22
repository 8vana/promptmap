# PromptMap Design: Simple JBF-FORGE

## Status

Proposed architecture.

## Scope

This document defines a lightweight, PromptMap-native paper-to-attack workflow
inspired by JBF-FORGE from Jailbreak Foundry.

The goal is not to reproduce the full JBF-FORGE system. The goal is to extend
PromptMap's existing external `paper_attack_scaffold` into an LLM-assisted,
human-reviewed workflow that:

1. reads a paper or paper notes
2. extracts attack metadata and algorithm steps
3. generates a PromptMap-compatible attack implementation draft
4. audits the draft against the extracted plan
5. emits staging artifacts for human review and promotion

Constraints:

- Keep `BaseAttack` unchanged.
- Keep `AttackContext` unchanged.
- Keep the workflow external to the runtime.
- Preserve the existing attack registry and benchmark model.

Out of scope:

- fully autonomous promotion into `promptmap/attacks/`
- guaranteed paper-fidelity matching JBF-FORGE
- end-to-end ASR reproduction of paper results
- replacing the existing `paper_attack_scaffold` with a mandatory runtime dependency

## Background

PromptMap already has:

- a stable runtime kernel based on `BaseAttack` and `AttackContext`
- an external `paper_attack_scaffold` tool that generates skeleton staging files
- attack registry metadata in YAML
- benchmark profiles for standardized evaluation

What PromptMap does not yet have is the "middle" between metadata entry and a
reviewable implementation draft.

JBF-FORGE provides the right conceptual reference:

- **Planner**: derive a complete implementation plan from paper material
- **Coder**: synthesize an executable attack from that plan
- **Auditor**: verify plan-to-code coverage and force refinement if needed

PromptMap should borrow that structure, but not the full operational weight of
JBF-FORGE.

## Design Goals

- Reuse the current staging-based onboarding workflow.
- Improve developer speed without pretending to guarantee correctness.
- Produce artifacts that fit PromptMap's current contracts immediately.
- Make uncertainty explicit rather than hiding it inside generated code.
- Keep all LLM use confined to tooling under `tools/`.
- Support gradual adoption: metadata-only first, code generation second, audit third.

## Non-Goals

- Rebuilding JBF-LIB concepts inside PromptMap.
- Supporting every jailbreak paper family from day one.
- Generating benchmark-ready attacks automatically.
- Making TUI settings the source of truth for tooling models.

## High-Level Architecture

```text
Paper / Notes / Optional Repo
          |
          v
Paper Preprocessor
  - fetch PDF or accept local text
  - normalize into markdown / excerpts
          |
          v
Planner
  - extract metadata
  - identify algorithm steps
  - infer PromptMap family + capabilities
  - produce implementation plan
          |
          v
Coder
  - generate PromptMap attack module draft
  - generate attack catalog draft
  - generate benchmark notes
          |
          v
Auditor
  - map plan steps to code sections
  - mark missing or ambiguous items
  - assign verdict
          |
          v
Staging Directory
  - attack_module.py
  - attack_catalog.yaml
  - implementation_plan.md
  - coverage_report.md
  - review_checklist.md
  - benchmark_notes.md
  - manifest.json
```

This is still an external developer workflow.

## Relationship to Existing Scaffold Tool

The current `paper_attack_scaffold` remains the foundation.

Current behavior:

- operator supplies metadata manually
- tool emits a skeleton module and related staging files

Proposed Simple JBF-FORGE behavior:

- operator may still supply metadata manually
- tool may additionally ingest paper text or a paper URL
- planner enriches or fills missing metadata
- coder generates a more specific implementation draft
- auditor produces explicit coverage notes

This means the evolution path is additive:

1. existing scaffold mode remains available
2. new forge mode is introduced as an optional workflow

## Why "Simple"

This design deliberately avoids several heavyweight JBF-FORGE traits:

- no dependence on Cursor Agent
- no hard requirement for multiple distinct frontier models
- no mandatory OCR service
- no mandatory reference repository retrieval
- no automatic matched ASR evaluation in the initial version
- no "fidelity = 100%" acceptance claim

Instead, the system aims for:

- high-quality plan extraction
- better-than-skeleton code generation
- explicit uncertainty reporting

## Core Workflow

### Step 1. Ingest

Accept one or more of:

- `--paper-url`
- `--pdf-path`
- `--paper-text-path`
- `--notes-path`

Optional:

- `--reference-repo-url`
- `--attack-id`
- `--display-name`
- `--family`

The operator may provide some metadata up front. Missing fields are planner
responsibility.

### Step 2. Normalize

Convert the input into a normalized working bundle:

- `paper.md`
- `paper_excerpt.json`
- `input_manifest.json`

Normalization responsibilities:

- strip irrelevant sections when possible
- preserve appendix prompt strings
- retain section headings and citations for traceability
- record source provenance for every extracted claim

Initial implementation does **not** implement OCR.

Initial implementation starts with:

- local markdown or plaintext input
- manually supplied excerpts
- arXiv abstract fetch as helper input

Initial PDF ingestion target:

- `--pdf-path` uses **Docling** as the default PDF-to-Markdown / JSON backend
- Docling output is written to `paper.md` and `paper.json`
- planner logic reads `paper.md` primarily and uses `paper.json` for provenance
  and future evidence enrichment

OCR is a later enhancement because:

- it adds operational complexity and provider coupling
- extraction errors can silently degrade plan quality
- PromptMap can reach a useful planner/coder/auditor MVP without it

### Step 3. Planner

The planner is the most important stage.

It produces a structured implementation plan with:

- attack summary
- paper metadata
- inferred PromptMap family
- target assumptions
- required capabilities
- parameter candidates
- algorithm steps in execution order
- prompt templates or prompt fragments found in paper
- ambiguities and open questions
- benchmark suitability recommendation

Suggested output files:

- `implementation_plan.md`
- `implementation_plan.json`

### Step 4. Coder

The coder takes:

- implementation plan
- current PromptMap `BaseAttack` contract
- example attacks in the repo
- current attack catalog schema

And generates:

- `attack_module.py`
- `attack_catalog.yaml`
- updated `benchmark_notes.md`

The coder is not asked to produce final, trusted code. It is asked to produce a
draft that is:

- syntactically valid
- structurally aligned with PromptMap
- traceable back to plan steps
- explicit about TODOs and uncertainties

### Step 5. Auditor

The auditor compares:

- implementation plan
- generated code
- generated catalog

And emits:

- `coverage_report.md`
- `audit_verdict.json`
- a refined `review_checklist.md`

The auditor should answer:

- which plan steps are implemented
- which are partially implemented
- which are missing
- which assumptions appear unsupported by the paper
- whether the attack should remain `supports_benchmark: false`

### Step 6. Human Review

A developer inspects staging artifacts and decides whether to:

- refine locally
- rerun coder with guidance
- rerun planner with more input
- abandon the candidate
- promote to the runtime

## Artifact Model

Existing scaffold artifacts:

- `attack_module.py`
- `attack_catalog.yaml`
- `benchmark_notes.md`
- `review_checklist.md`
- `manifest.json`

New artifacts to add:

- `implementation_plan.md`
- `implementation_plan.json`
- `coverage_report.md`
- `audit_verdict.json`
- `paper.md`
- `input_manifest.json`

Recommended staging layout:

```text
staging/
  attacks/
    <attack_id>/
      paper.md
      input_manifest.json
      implementation_plan.md
      implementation_plan.json
      attack_module.py
      attack_catalog.yaml
      benchmark_notes.md
      coverage_report.md
      audit_verdict.json
      review_checklist.md
      manifest.json
```

## Proposed Tool Layout

```text
tools/
  paper_attack_scaffold/
    README.md
    __main__.py
    templates/
      ...
  paper_attack_forge/
    README.md
    __main__.py
    llm_client.py
    ingest.py
    planner.py
    coder.py
    auditor.py
    models.py
    prompts/
      planner_system.txt
      planner_user.txt
      coder_system.txt
      coder_user.txt
      auditor_system.txt
      auditor_user.txt
```

Alternative:

- keep a single `paper_attack_scaffold` package and add subcommands

Recommended approach:

- keep one tool namespace and add explicit subcommands:
  - `scaffold`
  - `plan`
  - `forge`
  - `audit`

This avoids fragmenting documentation and lets developers enter through one CLI.

## CLI Shape

Recommended CLI:

```bash
python -m tools.paper_attack_scaffold scaffold ...
python -m tools.paper_attack_scaffold plan ...
python -m tools.paper_attack_scaffold forge ...
python -m tools.paper_attack_scaffold audit ...
```

### `scaffold`

Current metadata-only mode.

### `plan`

Example:

```bash
python -m tools.paper_attack_scaffold plan \
  --attack-id radial \
  --paper-text-path papers/radial.md \
  --provider bedrock \
  --model anthropic.claude-3-5-sonnet-20241022-v2:0
```

Outputs:

- normalized paper
- implementation plan
- inferred metadata draft

### `forge`

Example:

```bash
python -m tools.paper_attack_scaffold forge \
  --attack-id radial \
  --paper-text-path papers/radial.md \
  --provider bedrock \
  --model anthropic.claude-3-5-sonnet-20241022-v2:0
```

Outputs:

- plan
- generated attack module
- catalog draft
- benchmark notes
- checklist

### `audit`

Example:

```bash
python -m tools.paper_attack_scaffold audit \
  --staging-dir staging/attacks/radial \
  --provider bedrock \
  --model anthropic.claude-3-5-sonnet-20241022-v2:0
```

Outputs:

- coverage report
- verdict
- revised checklist

## LLM Configuration

This workflow uses LLMs, but it should not depend implicitly on TUI settings.

Recommended rule:

- tooling model selection is explicit via CLI flags or environment variables

Example:

- `--provider bedrock`
- `--model anthropic.claude-3-5-sonnet-20241022-v2:0`

Optional environment variables:

- `PROMPTMAP_FORGE_PROVIDER`
- `PROMPTMAP_FORGE_MODEL`
- `PROMPTMAP_FORGE_AUDIT_MODEL`

Why not reuse TUI settings directly:

- the tool is external to the runtime
- staging workflows may need different models than red-team runs
- explicit CLI configuration improves reproducibility

Future enhancement:

- allow a `--use-settings` flag that reads PromptMap settings as defaults only

## Planner Output Schema

The planner should emit a structured object similar to:

```json
{
  "attack_id": "radial",
  "display_name": "RADIAL Attack",
  "paper_title": "Analyzing the Inherent Response Tendency of LLMs...",
  "paper_url": "https://arxiv.org/abs/2312.04127",
  "family": "single_turn",
  "target_modes": ["api", "stateless"],
  "required_capabilities": ["scorer_llm"],
  "supports_benchmark_recommendation": false,
  "source_of_truth_priority": ["paper", "operator_notes", "reference_repo"],
  "default_params": {
    "seed_prompt": ""
  },
  "evidence_summary": {
    "paper_evidence_count": 3,
    "repo_evidence_count": 1,
    "operator_note_count": 0
  },
  "algorithm_steps": [
    {
      "step_id": "S1",
      "title": "Construct instruction framing",
      "description": "Build the paper-defined request framing around the target objective.",
      "evidence_refs": ["paper:S3.2:1"],
      "status": "supported",
      "notes": []
    }
  ],
  "prompt_fragments": [
    {
      "name": "instruction_template",
      "text": "...",
      "evidence_refs": ["paper:appA:2"]
    }
  ],
  "ambiguities": [
    "Paper does not define a default stopping rule."
  ],
  "paper_evidence": [
    {
      "evidence_id": "paper:S3.2:1",
      "source_kind": "paper",
      "section": "3.2",
      "locator": "p.4",
      "quote_excerpt": "...",
      "interpretation": "Paper defines the top-level framing pattern.",
      "confidence": "high"
    }
  ],
  "repo_evidence": [
    {
      "evidence_id": "repo:attack_py:17-29",
      "source_kind": "reference_repo",
      "repo_url": "https://github.com/example/project",
      "path": "attacks/radial.py",
      "line_start": 17,
      "line_end": 29,
      "quote_excerpt": "...",
      "interpretation": "Repo suggests a default retry count omitted by the paper.",
      "confidence": "medium",
      "paper_aligned": "unknown"
    }
  ],
  "operator_notes": []
}
```

The exact schema can evolve, but it should always preserve:

- algorithm steps
- evidence provenance
- ambiguity tracking

### Evidence Separation Rules

`implementation_plan.json` should keep evidence in three distinct channels:

- `paper_evidence`
- `repo_evidence`
- `operator_notes`

And every plan element that relies on evidence should reference those records by
`evidence_id`.

### Proposed Evidence Record Schema

Paper evidence record:

```json
{
  "evidence_id": "paper:S3.2:1",
  "source_kind": "paper",
  "section": "3.2",
  "locator": "p.4",
  "quote_excerpt": "...",
  "interpretation": "Paper defines the top-level framing pattern.",
  "confidence": "high"
}
```

Reference repo evidence record:

```json
{
  "evidence_id": "repo:attack_py:17-29",
  "source_kind": "reference_repo",
  "repo_url": "https://github.com/example/project",
  "path": "attacks/radial.py",
  "line_start": 17,
  "line_end": 29,
  "quote_excerpt": "...",
  "interpretation": "Repo suggests a default retry count omitted by the paper.",
  "confidence": "medium",
  "paper_aligned": "unknown"
}
```

Operator note record:

```json
{
  "evidence_id": "note:1",
  "source_kind": "operator_note",
  "note": "Author clarified in issue #14 that retries were capped at 5.",
  "confidence": "medium"
}
```

### Step-Level Reference Shape

Each `algorithm_steps[*]` item should reference evidence records instead of
embedding source-specific freeform fields:

```json
{
  "step_id": "S2",
  "title": "Retry with reworded framing",
  "description": "If the target refuses, regenerate a softer wrapper and retry.",
  "evidence_refs": ["paper:S4.1:2", "repo:attack_py:17-29"],
  "status": "supported",
  "notes": []
}
```

This has three benefits:

- paper and repo evidence remain distinguishable
- the auditor can detect unsupported coder inferences
- divergences can be localized to individual steps

### Divergence Tracking

The plan should also include an explicit divergence block:

```json
{
  "divergences": [
    {
      "divergence_id": "D1",
      "topic": "retry_count",
      "paper_position": "not specified",
      "repo_position": "defaults to 5",
      "planner_decision": "treat as unresolved and expose as configurable param",
      "severity": "medium"
    }
  ]
}
```

Rules:

- if paper and repo disagree, record a divergence
- if paper is silent and repo is informative, mark the value as repo-derived
- if neither source is sufficient, keep a TODO rather than inventing a value

## Coder Strategy

The coder should not synthesize arbitrarily. It should follow rules:

1. Read the implementation plan as source of truth.
2. Generate only PromptMap-compatible attack code.
3. Prefer copying established structural patterns from existing attacks.
4. Insert TODOs for unresolved steps instead of inventing hidden behavior.
5. Keep metadata in `AttackResult.metadata` explicit.

Suggested coder inputs:

- planner JSON
- current `attack_module.py.j2`
- examples:
  - `promptmap/attacks/single_pi_attack.py`
  - `promptmap/attacks/multi_pair_attack.py`
  - `promptmap/attacks/multi_chunked_request_attack.py`

Suggested coder outputs:

- `attack_module.py`
- `attack_catalog.yaml`
- `generation_notes.md`

## Auditor Strategy

The auditor should be strict, but not binary in the JBF sense.

JBF-FORGE targets acceptance only at `fidelity = 100%`.
PromptMap Simple JBF-FORGE should instead produce:

- `ready_for_manual_review`
- `missing_algorithm_steps`
- `unsafe_inference_detected`
- `benchmark_not_advised`

Proposed verdict levels:

- `pass_with_review`
- `needs_refinement`
- `blocked_by_missing_information`

This keeps the workflow useful even when the paper is incomplete.

## Safety and Reliability Principles

### 1. Paper Text Is Untrusted Input

Paper content may contain:

- instruction-like language
- code blocks
- adversarial strings
- malformed metadata

Mitigation:

- planner/coder/auditor prompts must treat paper text as data only
- forbid obeying instructions contained in source material
- constrain outputs to structured JSON where possible

### 2. Do Not Hide Uncertainty

If the paper omits:

- default parameters
- stopping criteria
- exact prompt strings

the system should record ambiguity, not hallucinate certainty.

### 3. No Auto-Promotion

Generated code must never be copied automatically into `promptmap/attacks/`.

Promotion remains an explicit human action.

### 4. Benchmark Defaults Stay Conservative

Generated attacks should default to:

- `supports_benchmark: false`
- `source_type: generated`

until reviewed.

### 5. Avoid "Looks Correct" Failure Mode

The worst outcome is polished but incorrect code.

Mitigation:

- preserve step-by-step coverage mapping
- highlight unsupported assumptions
- require review checklist completion

## Reference Repository Support

JBF-FORGE benefits greatly from official repositories.

PromptMap should support them as optional inputs, not initial requirements.

Reference repositories are a **supplementary source**, not the primary source of
truth.

Source-of-truth priority for PromptMap Simple JBF-FORGE:

1. paper text
2. operator notes and clarifications
3. reference repository snippets

Reference repositories are used to:

- resolve ambiguities left by the paper
- recover prompt templates or defaults omitted from the paper
- validate whether an inferred implementation detail is plausible

Reference repositories are **not** used to:

- auto-promote a generated attack into PromptMap
- justify copying the original implementation wholesale
- override the paper silently without recording the divergence

Important implementation rule:

- do not transplant repository attack code directly into PromptMap
- instead, translate paper-defined behavior into PromptMap's `BaseAttack` contract
- when repo material influences the draft, record that influence explicitly in
  plan and audit artifacts

Phase 1:

- no repo parsing
- operator may paste notes manually
- local `--paper-text-path` support
- local `--pdf-path` support via Docling
- no OCR in this phase

Phase 2:

- accept `--reference-repo-url`
- fetch selected files or snippets
- let planner cite repo evidence separately from paper evidence

Important rule:

- paper evidence and repo evidence must remain distinguishable
- paper-repo divergences must be surfaced explicitly

## Integration with Registry and Benchmark Layers

The forge workflow should integrate with existing Phase 1 and Phase 2 work:

- generated `attack_catalog.yaml` must conform to `AttackSpec`
- generated `attack_module.py` must match `BaseAttack`
- `benchmark_notes.md` should explain whether `supports_benchmark` can safely be flipped later

Future enhancement:

- `audit` can run local registry validation against the generated catalog
- `forge` can include a smoke-check against `python -m py_compile`

## Incremental Delivery Plan

### Phase A: Planner MVP

- add `plan` subcommand
- accept local markdown / text files
- support explicit LLM planning when provider/model are configured
- allow heuristic fallback for local or offline development
- emit `implementation_plan.md` and `implementation_plan.json`

Expected benefit:

- better metadata quality than manual scaffolding

### Phase B: Coder MVP

- add `forge` subcommand
- consume planner JSON
- generate `attack_module.py` and `attack_catalog.yaml`
- keep `supports_benchmark: false`

Expected benefit:

- developers start from a structured draft instead of a bare skeleton

### Phase C: Auditor MVP

- add `audit` subcommand
- produce coverage report and verdict
- update checklist

Expected benefit:

- clearer review and fewer silent gaps

### Phase D: Optional Repo Support

- ingest snippets from reference repos
- cite repo evidence separately

Expected benefit:

- better handling of papers with underspecified implementation details

### Phase E: Optional Local Verification

- `py_compile`
- registry YAML validation
- optional dry-run import

Expected benefit:

- faster feedback before promotion

## Risks and Mitigations

### Risk: Planner extracts the wrong algorithm

Mitigation:

- require evidence citations per step
- keep plan reviewable before coding

### Risk: Coder overfits to existing PromptMap attacks

Mitigation:

- include explicit "do not copy unrelated logic" instructions
- show algorithm step mapping in output notes

### Risk: Auditor rubber-stamps bad code

Mitigation:

- require line-referenced findings
- include "unsupported inference" as a first-class failure category

### Risk: Model/provider configuration becomes hard to reproduce

Mitigation:

- write provider/model fields to `manifest.json`
- keep CLI flags explicit

### Risk: Tooling becomes too heavy for normal development

Mitigation:

- keep metadata-only scaffold mode
- make planning/forging/auditing opt-in subcommands

## Success Criteria

The design is successful if:

- developers can go from paper text to reviewable attack draft faster than manual scaffolding
- generated drafts conform to PromptMap contracts without touching runtime APIs
- ambiguity is made visible instead of hidden
- generated attacks remain clearly separated from reviewed production attacks

## Recommendation

Implement the Simple JBF-FORGE workflow by evolving the current
`paper_attack_scaffold` tool into a subcommand-based external workflow:

1. keep `scaffold` as the manual baseline
2. add `plan`
3. add `forge`
4. add `audit`

This gives PromptMap the core benefits of JBF-FORGE:

- structured planning
- code generation guided by contracts
- explicit auditing

without inheriting the full weight and operational complexity of the original
system.
