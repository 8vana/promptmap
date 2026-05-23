# PromptMap Design: M5 Repo Support

## Status

Proposed design for milestone M5.

## Goal

Add **optional reference repository support** to the `paper_attack_scaffold`
workflow so that:

- `plan` can use repository snippets as supplementary evidence
- `forge` can surface repo-derived defaults or prompt fragments explicitly
- `audit` can report paper/repo divergence more clearly

This milestone is not about copying repository code into PromptMap.
It is about making under-specified papers easier to interpret while preserving
PromptMap's review-first workflow.

## Non-Negotiable Rule

Reference repositories are a **supplementary source** only.

Source-of-truth priority stays:

1. paper text
2. operator notes / clarifications
3. reference repository snippets

The system must never:

- transplant repository attack code directly into PromptMap
- silently prefer repo code over paper evidence
- auto-promote code because a repository exists

## Why M5 Is Needed

Current workflow works well when the paper explains:

- attack structure
- parameters
- prompt strings
- stopping rules

It struggles when the paper omits:

- full prompt templates
- dataset loading details
- retry counts
- naming of internal stages
- exact defaults used in experiments

Many jailbreak papers are in that second category.
M5 exists to narrow that gap without sacrificing provenance.

## Scope

M5 adds support for:

- `--reference-repo-url`
- `--reference-path`
- optional allowlisted file selection
- repository snippet extraction
- `repo_evidence` population
- divergence reporting between paper and repo

M5 does not add:

- full repository ingestion by default
- repository-wide semantic parsing
- arbitrary code execution from a fetched repository
- automatic implementation merge from repo code into `attack_module.py`

## User Experience

### Planner Inputs

`plan` should accept optional repo inputs:

```bash
python -m tools.paper_attack_scaffold plan \
  --attack-id radial \
  --pdf-path papers/radial.pdf \
  --paper-url "https://arxiv.org/abs/2312.04127" \
  --reference-repo-url "https://github.com/example/radial" \
  --reference-path attacks/radial.py \
  --reference-path README.md
```

Meaning:

- `--reference-repo-url`
  declares the canonical supplementary repo
- `--reference-path`
  narrows the repo to selected files only

If no `--reference-path` values are supplied, the tool should either:

- inspect a small default set
  such as `README*`, `attack*.py`, `main*.py`, `config*.yaml`
- or require explicit file selection in strict mode

## Proposed Workflow Changes

```text
paper / pdf / notes / optional repo
            |
            v
ingest
  - normalize paper
  - load repo snippets
            |
            v
planner
  - build paper_evidence
  - build repo_evidence
  - record divergences
            |
            v
forge
  - preserve repo-derived hints explicitly
            |
            v
audit
  - verify repo influence is explicit
  - flag silent repo-driven behavior
```

## Artifact Changes

### New Input Artifact

Add:

- `reference_manifest.json`

Suggested contents:

```json
{
  "repo_url": "https://github.com/example/radial",
  "selected_paths": [
    "attacks/radial.py",
    "README.md"
  ],
  "fetch_mode": "selected_paths",
  "fetched_at": "2026-05-22T12:34:56Z"
}
```

### Existing Plan Artifact

`implementation_plan.json` already supports:

- `repo_evidence`
- `divergences`

M5 should start populating them consistently.

### Staging Layout

Suggested additions:

```text
staging/
  attacks/
    <attack_id>/
      reference_manifest.json
      reference_snippets/
        README.md
        attacks__radial.py.txt
```

`reference_snippets/` should contain **normalized text snippets**, not a cloned
Git repository.

## Repo Evidence Model

The existing `EvidenceRecord` is already close enough:

```json
{
  "evidence_id": "repo:attacks_radial_py:17-29",
  "source_kind": "reference_repo",
  "repo_url": "https://github.com/example/radial",
  "path": "attacks/radial.py",
  "line_start": 17,
  "line_end": 29,
  "quote_excerpt": "...",
  "interpretation": "Repo suggests a default retry count omitted by the paper.",
  "confidence": "medium",
  "paper_aligned": "unknown"
}
```

M5 should establish rules for:

- evidence id generation
- line-based excerpts
- confidence assignment
- `paper_aligned` values

### `paper_aligned` Values

Recommended values:

- `yes`
- `no`
- `unknown`

Rules:

- `yes`
  repo detail matches paper wording or fills a paper omission cleanly
- `no`
  repo contradicts paper
- `unknown`
  could not determine alignment safely

## Divergence Rules

When paper and repo disagree, the planner should always record a divergence.

Example:

```json
{
  "divergence_id": "D1",
  "topic": "retry_count",
  "paper_position": "not specified",
  "repo_position": "defaults to 5",
  "planner_decision": "treat as unresolved and expose as configurable param",
  "severity": "medium"
}
```

Planner rules:

- if paper is explicit and repo conflicts:
  record divergence, favor paper
- if paper is silent and repo provides a usable detail:
  record repo evidence, treat as hint, not truth
- if repo logic is too coupled to another framework:
  record ambiguity, do not translate automatically

## Ingest Design

### Recommended Implementation Shape

Add a small repo ingestion layer under `tools/paper_attack_scaffold/`:

```text
repo_ingest.py
```

Responsibilities:

- parse GitHub URL
- accept local extracted repo path in future
- fetch or read selected files
- normalize them into plain text snippets
- emit `reference_manifest.json`
- return structured repo snippet records to planner

### Initial Backends

Phase D should support two backends:

1. `--reference-path` from a local working tree path
2. `--reference-repo-url` from GitHub text fetch

Recommended first implementation:

- GitHub raw file fetch only
- no full git clone
- no submodules
- no large-binary handling

This keeps the workflow lightweight and auditable.

## CLI Changes

### `plan`

Add:

- `--reference-repo-url`
- `--reference-path` repeatable
- `--reference-branch` optional

Optional later:

- `--reference-manifest-path`

### `forge`

No new required flags.

It should simply consume `repo_evidence` and `divergences` if present.

### `audit`

No new required flags.

It should read `repo_evidence` and check whether:

- repo influence is surfaced in generated metadata or notes
- any repo-derived values were used silently

## Planner Changes

Planner should evolve in four ways.

### 1. Accept Repo Snippets As Separate Input Channel

Do not mix repo text into `paper.md`.

Instead, pass it separately to planner logic:

- `paper_markdown`
- `repo_snippets`
- `notes_text`

### 2. Populate `repo_evidence`

Repo snippets should become `EvidenceRecord`s with:

- `source_kind = "reference_repo"`
- file path
- line span
- excerpt
- repo URL

### 3. Record Divergences

If repo-derived defaults appear to refine a paper omission, planner should:

- keep ambiguity if still uncertain
- add repo evidence
- optionally add divergence

### 4. Preserve Paper-First Normalization

Normalization order should be:

- infer from paper first
- enrich from repo second
- annotate where repo influenced the plan

## Forge Changes

Forge should remain conservative.

M5 should not make forge "copy repo code."

Instead, forge should use repo evidence only to:

- fill named constants
- fill draft defaults
- enrich `generation_notes.md`
- expose extra TODO context

### Allowed Repo Influence

Allowed:

- `DEFAULT_PARAMS` hint values
- prompt fragments promoted to named constants
- comments/TODOs citing repo evidence ids

Not allowed:

- bulk-copying helper functions
- transplanting whole attack logic
- removing TODOs solely because repo code exists

### Example

If repo shows:

- `top_k = 4`

forge may emit:

```python
DEFAULT_PARAMS = {
    "selected_instruction_count": 4,  # repo-derived hint; verify against paper
}
```

and record that in `generation_notes.md`.

## Audit Changes

Audit should expand to check:

- whether repo-derived fields are explicit
- whether repo-derived defaults were surfaced in metadata or notes
- whether any divergence was ignored silently

### New Audit Category

Recommended optional category:

- `silent_repo_dependency_detected`

Use it when:

- code behavior appears repo-driven
- but no corresponding `repo_evidence` or divergence is exposed

## Safety Constraints

### 1. No Arbitrary Code Execution

Repo support must not run imported repository code.

Only fetch/read text.

### 2. No Silent Trust Upgrade

Presence of a repo must not upgrade:

- `supports_benchmark`
- `source_type`
- `verdict`

without explicit logic.

### 3. No Whole-Repo Dumping Into LLM Context

If LLM use is added later, pass only:

- selected snippets
- normalized excerpts
- explicit provenance labels

Not:

- entire repos by default

## Recommended Implementation Order

### Step 1

Add `repo_ingest.py` with:

- GitHub raw fetch support
- local-file support
- selected-path normalization

### Step 2

Add CLI flags to `plan`.

### Step 3

Emit:

- `reference_manifest.json`
- `reference_snippets/`

### Step 4

Populate `repo_evidence` and `divergences`.

### Step 5

Teach `forge` to surface repo-derived hints in:

- `DEFAULT_PARAMS`
- `generation_notes.md`

### Step 6

Teach `audit` to detect silent repo influence.

## Success Criteria

M5 is successful if:

- papers with underspecified defaults produce better plans
- repo and paper provenance remain clearly separated
- divergences are explicit
- forge becomes more informative without becoming less conservative
- audit can explain repo influence to human reviewers

## Recommendation

Implement M5 as a **planner-first** enhancement.

The most important thing is not fetching repos.
The most important thing is preserving:

- explicit provenance
- paper-first priority
- reviewable divergences

If that is preserved, repo support will strengthen the current workflow rather
than making it opaque.
