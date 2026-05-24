# Workflow Status: radial_e2e

## Stage

- `workflow_stage`: `benchmark_candidate`
- `workflow_profile`: `single_turn`

## Phase Presence

- `plan`: `true`
- `forge`: `true`
- `audit`: `true`
- `verify`: `true`

## Completion Checks

- `pipeline_complete`: `true`
- `runnable_draft_ready`: `true`
- `review_ready`: `true`
- `promotion_ready`: `true`
- `benchmark_candidate`: `true`

## Profile Checks

### single_turn

- `applicable`: `true`
- `supported_skeleton`: `true`
- `workflow_profile_aligned`: `true`
- `verify_single_turn_ok`: `true`
- `supported_skeletons`: `['single_turn_template', 'single_turn_splice', 'dataset_rank_then_attack']`


## Phase Summaries

- `planner_backend_used`: `llm`
- `forge_backend_used`: `llm`
- `execution_skeleton`: `dataset_rank_then_attack`
- `audit_verdict`: `pass_with_review`
- `verify_verdict`: `pass`

## Recommended Actions

- Workflow criteria are satisfied for the current staging target.
