# PromptMap Design: Benchmark Mode, Attack Registry, and Paper-Attack Tooling

## Status

Proposed architecture.

## Scope

This document defines the design for the following additions to PromptMap:

1. Add a benchmark mode.
2. Introduce attack registry and metadata management.
3. Add an external paper-attack scaffolding tool.

Constraint:

- The public runtime API must keep the current `BaseAttack` and `AttackContext` contracts unchanged.

Out of scope:

- Replacing the existing attack execution model.
- Replacing the current `promptmap` TUI.
- Fully autonomous paper-to-code generation in the core runtime.

## Design Goals

- Preserve the current public API exported from `promptmap.__init__`.
- Keep existing attacks runnable with minimal or no modifications.
- Separate exploratory red teaming from standardized benchmarking.
- Make attack inventory queryable and machine-readable.
- Make it easier to add new research attacks without coupling that workflow to the core runtime.

## Current Constraints

PromptMap currently has:

- A stable attack interface: `BaseAttack.run(ctx, objective, **kwargs) -> AttackResult`.
- A stable runtime dependency bundle: `AttackContext`.
- Static attack registration in `promptmap/cli.py`.
- A signatures-driven red-team data model centered on `datasets/signatures.yaml`.
- A single scorer abstraction, currently `LLMJudgeScorer`.
- A special autonomous `agent` path that is not a normal attack primitive in the same sense as `single_pi`, `pair`, or `tap`.

This means the design should add new orchestration and metadata layers around attacks, not inside the `BaseAttack` contract.

## High-Level Architecture

The proposed architecture adds three layers around the existing runtime:

```text
PromptMap Runtime
  BaseAttack / AttackContext / TargetAdapter / Scorer
        ^
        |
Attack Registry Layer
  AttackSpec / AttackRegistry / catalog YAML / discovery
        ^
        |
Benchmark Layer
  BenchmarkProfile / BenchmarkRunner / standardized outputs
        ^
        |
External Tooling Layer
  paper-attack scaffold tool
```

The runtime remains the execution kernel.

## Important Distinction: Attack vs Execution Mode

PromptMap has two different concepts that must not be conflated:

- **Attack primitive**
  - A concrete prompt-execution strategy such as `single_pi`, `crescendo`, `pair`, `tap`, or `chunked_request`.
  - These are the units that belong in the attack registry.
- **Execution mode / orchestrator**
  - A higher-level controller that decides how to use attacks.
  - The current `agent` behavior belongs here: it autonomously selects from available attack primitives and runs them.

Therefore:

- `agent` must **not** be modeled as a benchmarkable attack primitive.
- `agent` should **not** live in the same registry category as `single_pi` or `pair`.
- benchmark mode should operate on attack primitives, not orchestrators.

This design uses:

- an **attack registry** for attack primitives
- an optional **execution-mode registry** for orchestrators such as `agent`

## 1. Attack Registry and Metadata

### Intent

Turn attacks from a static list of import paths into a structured catalog that can drive:

- CLI choices
- TUI display
- attack-agent tool descriptions
- benchmark eligibility
- target compatibility filtering
- paper-attack onboarding

### Core Principle

The registry is an internal catalog layer. It does not change the `BaseAttack` interface.

### New Internal Types

Add a new internal package:

```text
promptmap/
  registry/
    __init__.py
    attack_registry.py
    attack_spec.py
    mode_registry.py
    mode_spec.py
```

Proposed `AttackSpec` fields:

```python
from dataclasses import dataclass, field

@dataclass(frozen=True)
class AttackSpec:
    attack_id: str                  # stable runtime id, e.g. "pair"
    import_path: str                # "promptmap.attacks.multi_pair_attack:PAIRAttack"
    registered_name: str            # e.g. "Multi_PAIR_Attack"
    display_name: str               # e.g. "PAIR Attack"
    family: str                     # single_turn | multi_turn | autonomous
    description: str
    source_type: str                # builtin | contributed | generated
    paper_title: str = ""
    paper_url: str = ""
    paper_year: int | None = None
    prompt_technique_aware: bool = False
    supports_benchmark: bool = True
    target_modes: list[str] = field(default_factory=list)
    # e.g. ["api", "browser", "stateless", "stateful"]
    required_capabilities: list[str] = field(default_factory=list)
    # e.g. ["scorer_llm", "adversarial_llm", "tool_calling"]
    tags: list[str] = field(default_factory=list)
    default_params: dict = field(default_factory=dict)
    benchmark_defaults: dict = field(default_factory=dict)
    compatible_atlas_techniques: list[str] = field(default_factory=list)
```

Proposed `ModeSpec` fields:

```python
@dataclass(frozen=True)
class ModeSpec:
    mode_id: str                    # e.g. "manual", "agent"
    display_name: str
    description: str
    kind: str                       # manual | orchestrated
    import_path: str = ""
    supports_tui: bool = True
    supports_cli: bool = True
    supports_benchmark: bool = False
```

Notes:

- `manual` is the normal mode where the user explicitly picks one attack primitive.
- `agent` is an orchestrated mode that selects attack primitives autonomously.
- only attack primitives belong in `AttackRegistry`
- `agent` belongs in `ModeRegistry`

### Metadata Source

Use catalog YAML files instead of embedding metadata in attack classes.

Proposed layout:

```text
promptmap/catalog/
  attacks/
    single_pi.yaml
    crescendo.yaml
    pair.yaml
    tap.yaml
    chunked_request.yaml
  modes/
    manual.yaml
    agent.yaml
```

Reasons:

- Keeps `BaseAttack` unchanged.
- Allows richer metadata without touching attack modules.
- Makes generated and contributed attacks easier to review.
- Supports future automation and linting.

Example catalog entry:

```yaml
attack_id: pair
import_path: promptmap.attacks.multi_pair_attack:PAIRAttack
registered_name: Multi_PAIR_Attack
display_name: PAIR Attack
family: multi_turn
description: Iterative adversarial prompt refinement driven by attacker feedback.
source_type: builtin
paper_title: Jailbreaking Black Box LLMs in Twenty Queries
paper_url: https://arxiv.org/abs/2310.08419
paper_year: 2023
prompt_technique_aware: true
supports_benchmark: true
target_modes: [api, browser, stateful]
required_capabilities: [scorer_llm, adversarial_llm]
tags: [jailbreak, iterative, research]
default_params:
  max_iterations: 20
  threshold: 0.7
benchmark_defaults:
  max_iterations: 10
  threshold: 0.7
```

### Registry Responsibilities

`AttackRegistry` should:

- load catalog YAML
- validate unique `attack_id`
- validate import paths
- lazily import attack classes
- instantiate attacks
- filter attacks by metadata
- expose a compatibility view for CLI, TUI, and benchmark mode

Proposed methods:

```python
class AttackRegistry:
    def list_specs(self) -> list[AttackSpec]: ...
    def get_spec(self, attack_id: str) -> AttackSpec: ...
    def load_class(self, attack_id: str) -> type[BaseAttack]: ...
    def create(self, attack_id: str, **kwargs) -> BaseAttack: ...
    def list_for_target_mode(self, mode: str) -> list[AttackSpec]: ...
    def list_benchmarkable(self) -> list[AttackSpec]: ...
```

### Backward Compatibility

The current `_ATTACKS` mapping in `promptmap/cli.py` becomes a shim generated from the registry.

Phase 1 behavior:

- Keep the same CLI attack ids: `single_pi`, `crescendo`, `pair`, `tap`, `chunked_request`, `agent`.
- Replace static `_ATTACKS` with registry-backed lookup.

This preserves existing user-facing CLI behavior.

### Registry Validation

Add integrity checks:

- duplicate `attack_id`
- invalid import path
- imported class is not a `BaseAttack`
- `supports_benchmark: true` without benchmark defaults
- `required_capabilities` contains unknown values
- `target_modes` contains unknown values

## 2. Benchmark Mode

### Intent

Benchmark mode is a standardized measurement lane, not a replacement for red-team mode.

It should answer:

- Did safety regress between versions?
- Which attacks are strongest under fixed conditions?
- How do targets compare under a consistent scoring policy?

### Core Principle

Benchmark mode reuses the existing attack runtime:

- `BaseAttack`
- `AttackContext`
- `TargetAdapter`
- `BaseScorer`

It adds a standardized orchestration layer and versioned benchmark profiles.

### Runtime Shape

Add a new internal package:

```text
promptmap/
  benchmark/
    __init__.py
    profiles.py
    runner.py
    models.py
    reporters.py
```

### Benchmark Concepts

#### BenchmarkProfile

A benchmark profile defines:

- which objectives to use
- which attacks to run
- which attack params to freeze
- which scorer policy to use
- which language to use
- which targets are in scope

Proposed type:

```python
@dataclass(frozen=True)
class BenchmarkProfile:
    profile_id: str
    version: str
    dataset_source: str              # usually signatures.yaml
    objective_resolver: dict         # frozen subset selection
    attack_ids: list[str]
    attack_overrides: dict[str, dict]
    language: str
    scorer_policy: dict
    tags: list[str]
```

### Profiles and Dataset Strategy

Benchmark mode should not read the entire `signatures.yaml` as its test set.

Instead:

- `signatures.yaml` remains the canonical prompt catalog.
- benchmark profiles resolve a frozen or rolling subset from that catalog.

Proposed layout:

```text
promptmap/datasets/benchmark_profiles/
  stable_v1.yaml
  rolling_latest.yaml
```

Example stable profile:

```yaml
profile_id: stable_v1
version: "1"
dataset_source: signatures.yaml
language: en
objective_resolver:
  mode: frozen_list
  signature_refs:
    - atlas_technique: AML.T0051.000
      prompt_technique: role_play
      ordinal: 0
    - atlas_technique: AML.T0054
      prompt_technique: task_switch
      ordinal: 1
attack_ids: [single_pi, pair, tap, crescendo]
attack_overrides:
  pair:
    max_iterations: 10
  tap:
    max_branches: 8
scorer_policy:
  type: llm_judge
  threshold: 0.7
  prompt_profile: benchmark_v1
tags: [stable, ci]
```

Example rolling profile:

```yaml
profile_id: rolling_latest
version: "rolling"
dataset_source: signatures.yaml
language: en
objective_resolver:
  mode: rules
  per_technique_limit: 3
  include_prompt_techniques:
    - role_play
    - task_switch
    - instruction_override
attack_ids: [single_pi, pair, tap, crescendo]
attack_overrides: {}
scorer_policy:
  type: llm_judge
  threshold: 0.7
  prompt_profile: benchmark_v1
tags: [rolling, freshness]
```

### Benchmark Execution Model

The benchmark runner should:

1. load a target or target matrix
2. load a benchmark profile
3. resolve benchmark objectives from `signatures.yaml`
4. query the attack registry for benchmarkable attacks
5. create an `AttackContext`
6. run each attack against each objective
7. collect raw `AttackResult`
8. emit aggregate outputs

No changes are required to attack classes if:

- the runner passes `objective` the same way `promptmap-run` does
- benchmark-specific attack params are passed via `**kwargs`

### Benchmark Output Model

Add separate benchmark outputs from normal JSONL attack logs.

Proposed outputs:

```text
.promptmap/
  benchmarks/
    20260521T120000Z_<run_id>/
      manifest.json
      raw_results.jsonl
      aggregate.json
      attack_summary.csv
      objective_summary.csv
      target_summary.csv
```

Suggested aggregate metrics:

- success rate by attack
- success rate by target
- success rate by prompt technique
- average turns
- average score
- failure counts

### Benchmark CLI

Do not overload the existing `promptmap-run` semantics too early.

Recommended initial interface:

```text
promptmap-benchmark
```

Example:

```bash
promptmap-benchmark \
  --target-config target_config.yaml \
  --profile stable_v1 \
  --attacks pair,tap \
  --language en
```

Phase 2 can add:

- `promptmap-run --mode benchmark`
- TUI integration

### Benchmark Scorer Policy

Benchmark mode should freeze scoring configuration, not just attack selection.

Add scorer prompt profiles:

```text
promptmap/scorers/prompts/
  redteam_default.txt
  benchmark_v1.txt
```

`LLMJudgeScorer` remains the same public scorer type; benchmark mode simply injects a fixed prompt profile and threshold.

This preserves the scoring abstraction while improving comparability.

### Benchmark vs Red-Team Positioning

Red-team mode:

- exploratory
- user-driven or agent-driven
- broad prompt catalog
- target-specific quirks matter

Benchmark mode:

- fixed and comparable
- profile-driven
- attack and scorer configs frozen
- outputs optimized for regression tracking

## 3. External Paper-Attack Scaffolding Tool

### Intent

Speed up the addition of research attacks without making the PromptMap runtime depend on OCR, paper parsing, or code-generation workflows.

### Core Principle

This tooling is external to the runtime.

It may live in the repository, but it must not be part of the public runtime API or required for normal attack execution.

### Placement

Recommended location:

```text
tools/
  paper_attack_scaffold/
    README.md
    __main__.py
    templates/
      attack_module.py.j2
      attack_catalog.yaml.j2
      review_checklist.md.j2
      benchmark_notes.md.j2
```

This keeps it clearly separate from `promptmap/`.

### Supported Workflow

The tool is intentionally human-in-the-loop.

#### Step 1. Ingest

Input:

- paper metadata
- optional paper text or notes
- manual choices from the operator

Example:

```bash
python -m tools.paper_attack_scaffold \
  --attack-id skeleton_key \
  --display-name "Skeleton Key Attack" \
  --paper-title "..." \
  --paper-url "https://arxiv.org/abs/..." \
  --family multi_turn
```

#### Step 2. Generate Staging Files

Output to a staging directory:

```text
staging/
  attacks/
    skeleton_key/
      attack_module.py
      attack_catalog.yaml
      benchmark_notes.md
      review_checklist.md
```

Generated artifacts:

- `attack_module.py`
  - a valid `BaseAttack` skeleton
  - `run(ctx, objective, **kwargs)` implemented as a stub or partial flow
- `attack_catalog.yaml`
  - registry metadata entry
- `benchmark_notes.md`
  - whether the attack is benchmark-suitable
- `review_checklist.md`
  - human validation checklist

#### Step 3. Human Review

A developer reviews:

- attack algorithm mapping
- compatibility with `AttackContext`
- target mode assumptions
- scoring assumptions
- benchmark suitability

#### Step 4. Promote

After review:

- copy the module into `promptmap/attacks/`
- copy the catalog file into `promptmap/catalog/attacks/`
- add tests

### Why External Instead of Core

- avoids runtime dependency bloat
- avoids coupling PromptMap execution to code-generation workflows
- avoids forcing every user to install tooling they do not need
- makes it safe to iterate on scaffolding prompts and templates independently

### Scaffolded Attack Contract

The scaffold tool must produce code that already conforms to the current runtime contract:

```python
class NewAttack(BaseAttack):
    async def run(self, ctx: AttackContext, objective: str, **kwargs) -> AttackResult:
        ...
```

It must never invent a new base class.

### Optional Future Modes

Future versions may support:

- metadata-only generation
- attack skeleton plus pytest skeleton
- benchmark eligibility suggestions
- assisted mapping from paper families to existing PromptMap attack families

But the initial version should stay deliberately narrow.

## File Layout Summary

Proposed additions:

```text
promptmap/
  benchmark/
    __init__.py
    models.py
    profiles.py
    runner.py
    reporters.py
  registry/
    __init__.py
    attack_spec.py
    attack_registry.py
  catalog/
    attacks/
      single_pi.yaml
      crescendo.yaml
      pair.yaml
      tap.yaml
      chunked_request.yaml
      agent.yaml
  datasets/
    benchmark_profiles/
      stable_v1.yaml
      rolling_latest.yaml
  scorers/
    prompts/
      benchmark_v1.txt

tools/
  paper_attack_scaffold/
    README.md
    __main__.py
    templates/
      attack_module.py.j2
      attack_catalog.yaml.j2
      review_checklist.md.j2
      benchmark_notes.md.j2
```

## Migration Plan

### Phase 1: Registry First

- add registry package and catalog YAML
- move CLI attack lookup to registry-backed resolution
- keep all user-facing attack ids unchanged for attack primitives
- move `agent` to a mode registry instead of the attack registry
- keep TUI behavior unchanged

Expected benefit:

- attack inventory becomes queryable with zero public API breakage

### Phase 2: Benchmark Headless MVP

- add benchmark profile loader
- add benchmark runner
- add `promptmap-benchmark`
- emit manifest + raw + aggregate outputs

Expected benefit:

- standardized regression lane without touching attack implementations

Initial UX scope:

- benchmark mode is **CLI/headless only**
- TUI does not need to expose benchmark mode in this phase

### Phase 3: TUI and Agent Integration

- show registry metadata in TUI
- let attack agent use registry descriptions instead of ad hoc docstrings
- expose benchmark runs in TUI
- expose execution-mode selection in TUI, distinguishing manual vs agent

Expected benefit:

- consistent UX across all run modes

### Phase 4: External Scaffolding Tool

- add staging generator under `tools/`
- generate attack skeleton + catalog entry + review checklist
- document promotion workflow

Expected benefit:

- faster onboarding of research attacks with low runtime risk

## Compatibility Guarantees

The following remain unchanged:

- `BaseAttack`
- `AttackContext`
- `TargetAdapter`
- `AttackResult`
- `ScorerResult`
- `Message`

Registry and benchmark layers are additive and internal.

## Risks and Mitigations

### Risk: Attack metadata drifts from implementation

Mitigation:

- add registry validation tests
- require every catalog entry to import successfully
- prefer defaults in catalog only for orchestration, not as hidden runtime truth

### Risk: Benchmark mode becomes a second, inconsistent runtime

Mitigation:

- reuse `BaseAttack.run`
- reuse `AttackContext`
- reuse target adapters and scorers
- keep benchmark logic limited to orchestration, selection, and reporting

### Risk: Generated paper attacks are low quality

Mitigation:

- keep the tool external
- require human review before promotion
- generate checklists and metadata, not just code

### Risk: Stable benchmark profiles become stale

Mitigation:

- explicitly support both stable and rolling profiles
- version stable profiles instead of mutating them

## Recommended First Implementation Slice

To minimize risk, implement in this order:

1. Attack registry and catalog YAML.
2. Benchmark profile resolution from `signatures.yaml`.
3. Headless benchmark runner and output format.
4. External paper-attack scaffold tool.

This sequence delivers value early while keeping the public runtime stable.
