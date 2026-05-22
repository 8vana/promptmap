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

`scaffold` is the original metadata-first skeleton generator.

`plan` is the Phase A Simple JBF-FORGE planner. It normalizes paper material and
emits an implementation plan with evidence separation.

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
