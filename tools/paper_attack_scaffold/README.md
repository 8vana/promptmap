# Paper Attack Scaffold

`paper_attack_scaffold` is a developer-facing helper for onboarding a research
attack into PromptMap.

It is intentionally external to the runtime:

- it does not change `BaseAttack`
- it does not change `AttackContext`
- it is not required for normal `promptmap` execution

## Modes

The tool currently supports:

- `scaffold`
- `plan`
- `forge`
- `audit`
- `verify`

`scaffold` is the original metadata-first skeleton generator.

`plan` is the Phase A Simple JBF-FORGE planner. It normalizes paper material and
emits an implementation plan with evidence separation.

`forge` is the Phase B coder MVP. It consumes `implementation_plan.json` from a
staging directory and regenerates a plan-driven `attack_module.py` plus updated
catalog and review artifacts.

`audit` is the Phase C auditor MVP. It compares the implementation plan against
the generated module and catalog, then writes a coverage report and verdict.

`verify` is the promotion-oriented local verification layer. It performs
artifact checks such as import smoke, catalog schema validation, plan contract
validation, and reference artifact consistency checks.

## What `scaffold` generates

For a given attack id, the tool creates a staging directory containing:

- `attack_module.py`
- `attack_catalog.yaml`
- `benchmark_notes.md`
- `review_checklist.md`
- `manifest.json`

The generated module is a valid `BaseAttack` scaffold. It is runnable, but it is
only a baseline placeholder until a human maps the paper's actual algorithm.

## `scaffold` usage

```bash
python -m tools.paper_attack_scaffold scaffold \
  --attack-id skeleton_key \
  --display-name "Skeleton Key Attack" \
  --family multi_turn \
  --paper-title "Skeleton Key: ..."
```

Optional metadata:

```bash
python -m tools.paper_attack_scaffold scaffold \
  --attack-id skeleton_key \
  --display-name "Skeleton Key Attack" \
  --family multi_turn \
  --paper-title "Skeleton Key: ..." \
  --paper-url "https://arxiv.org/abs/2402.XXXX" \
  --paper-year 2024 \
  --description "Research attack scaffold for paper reproduction." \
  --target-modes api,browser,stateful \
  --required-capabilities scorer_llm,adversarial_llm \
  --tags generated,research,jailbreak \
  --compatible-atlas-techniques AML.T0051.000,AML.T0054 \
  --default-param max_iterations=20 \
  --benchmark-param max_iterations=10
```

By default, output is written under:

```text
staging/attacks/<attack_id>/
```

Use `--output-dir` to change the staging root.

Legacy compatibility:

- calling `python -m tools.paper_attack_scaffold --attack-id ...` without a
  subcommand still behaves like `scaffold`

## What `plan` generates

For a given paper input, `plan` creates or enriches a staging directory with:

- `paper.md`
- `paper.json`
- `input_manifest.json`
- `implementation_plan.json`
- `implementation_plan.md`
- `manifest.json` updated with `planner_phase_a`

When reference repo inputs are supplied, `plan` also writes:

- `reference_manifest.json`
- `reference_snippets/`

Those snippets are passed to the planner as a separate supplementary channel
and may populate `repo_evidence` / `divergences` in
`implementation_plan.json`.

When LLM refinement is used, `plan` also stores:

- `raw_planner_output.json`
- `raw_planner_response.txt`

If `--pdf-path` is used, the planner expects **Docling** to be installed and
uses it to produce normalized Markdown and structured JSON.

## `plan` usage

From local markdown or plaintext:

```bash
python -m tools.paper_attack_scaffold plan \
  --attack-id radial \
  --paper-text-path papers/radial.md \
  --paper-url "https://arxiv.org/abs/2312.04127"
```

From a local PDF via Docling:

```bash
python -m tools.paper_attack_scaffold plan \
  --attack-id radial \
  --pdf-path papers/radial.pdf \
  --paper-url "https://arxiv.org/abs/2312.04127"
```

With optional supplementary repo hints:

```bash
python -m tools.paper_attack_scaffold plan \
  --attack-id radial \
  --pdf-path papers/radial.pdf \
  --paper-url "https://arxiv.org/abs/2312.04127" \
  --reference-repo-url "https://github.com/example/radial" \
  --reference-path attacks/radial.py \
  --reference-path README.md
```

Or use a local extracted repo root instead of GitHub fetch:

```bash
python -m tools.paper_attack_scaffold plan \
  --attack-id radial \
  --paper-text-path papers/radial.md \
  --reference-root /path/to/reference-repo \
  --reference-path attacks/radial.py
```

Optional LLM-assisted refinement:

```bash
python -m tools.paper_attack_scaffold plan \
  --attack-id radial \
  --paper-text-path papers/radial.md \
  --paper-url "https://arxiv.org/abs/2312.04127" \
  --provider bedrock \
  --model anthropic.claude-3-5-sonnet-20241022-v2:0
```

Planner behavior:

- `--planner-backend auto`
  Uses LLM refinement when `--provider` and `--model` are supplied; otherwise
  falls back to heuristic planning.
- `--planner-backend heuristic`
  Uses the local heuristic planner only.
- `--planner-backend llm`
  Requires a configured provider/model and fails if the LLM path cannot run.

Reference repo behavior:

- `--reference-repo-url`
  Declares a supplementary GitHub repository for later repo evidence ingestion.
- `--reference-path`
  Narrows repo support to explicit repo-relative files.
- `--reference-root`
  Uses a local extracted repo directory instead of GitHub fetch.
- `--reference-branch`
  Selects a GitHub branch for raw-file fetch mode.

## `forge` usage

Run `forge` after `plan` has produced `implementation_plan.json`.

From an attack id under the default staging root:

```bash
python -m tools.paper_attack_scaffold forge \
  --attack-id radial \
  --output-dir staging/attacks \
  --force
```

Or point directly at a staging directory:

```bash
python -m tools.paper_attack_scaffold forge \
  --staging-dir staging/attacks/radial \
  --force
```

Optional LLM-assisted forge:

```bash
python -m tools.paper_attack_scaffold forge \
  --attack-id radial \
  --output-dir staging/attacks \
  --forge-backend auto \
  --provider bedrock \
  --model anthropic.claude-3-5-sonnet-20241022-v2:0 \
  --force
```

`forge` supports:

- `--forge-backend heuristic`
  Uses the local deterministic coder only.
- `--forge-backend llm`
  Requires a configured provider/model and fails if the LLM path cannot run.
- `--forge-backend auto`
  Uses LLM refinement when configured, else falls back to heuristic forge.

Even in LLM mode, the tool keeps the heuristic forge as a safe fallback and
preserves explicit TODOs and ambiguities.

It writes:

- `attack_module.py`
- `attack_catalog.yaml`
- `benchmark_notes.md`
- `review_checklist.md`
- `generation_notes.md`
- `raw_forge_output.json` when LLM forge is used
- `raw_forge_response.txt` when LLM forge is used
- `manifest.json` updated with `forge_phase_b`

## `audit` usage

Run `audit` after `forge` has produced `attack_module.py` and `attack_catalog.yaml`.

```bash
python -m tools.paper_attack_scaffold audit \
  --attack-id radial \
  --output-dir staging/attacks \
  --force
```

Or point directly at a staging directory:

```bash
python -m tools.paper_attack_scaffold audit \
  --staging-dir staging/attacks/radial \
  --force
```

`audit` currently uses a local heuristic auditor. It writes:

- `coverage_report.md`
- `audit_verdict.json`
- `review_checklist.md`
- `manifest.json` updated with `audit_phase_c`

## `verify` usage

Run `verify` after `forge`, or after manual refinement, to perform local
promotion checks on the staging artifacts.

```bash
python -m tools.paper_attack_scaffold verify \
  --attack-id radial \
  --output-dir staging/attacks \
  --force
```

Or point directly at a staging directory:

```bash
python -m tools.paper_attack_scaffold verify \
  --staging-dir staging/attacks/radial \
  --force
```

`verify` writes:

- `verification_report.md`
- `verification_report.json`
- `manifest.json` updated with `verification_phase_e`

## Evidence Model

`implementation_plan.json` separates evidence into:

- `paper_evidence`
- `repo_evidence`
- `operator_notes`

And step-level plan items refer to evidence by `evidence_refs`.

This keeps paper and reference repo provenance distinguishable and avoids
silently treating repository code as the primary source of truth.

## Promotion Workflow

1. Review `review_checklist.md`
2. Replace scaffold logic in `attack_module.py` with the actual paper flow
3. Validate metadata in `attack_catalog.yaml`
4. Promote files into:
   - `promptmap/attacks/<module_name>.py`
   - `promptmap/catalog/attacks/<attack_id>.yaml`
5. Add tests
6. Run repository validation

## Safety Notes

- New scaffolds default to `source_type: generated`
- `supports_benchmark` defaults to `false`
- the generated module includes `metadata["scaffold_status"] = "needs_review"`

That makes it harder to mistake a staging artifact for a production-complete attack.
