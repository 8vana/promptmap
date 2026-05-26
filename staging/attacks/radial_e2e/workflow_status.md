# Workflow Status: radial_e2e

## Stage

- `workflow_stage`: `promoted`
- `forge_status`: `promoted`
- `workflow_profile`: `single_turn`

## Phase Presence

- `plan`: `true`
- `forge`: `true`
- `audit`: `true`
- `verify`: `true`
- `promote`: `true`

## Completion Checks

- `pipeline_complete`: `true`
- `runnable_draft_ready`: `true`
- `review_ready`: `true`
- `promotion_ready`: `false`
- `benchmark_candidate`: `false`
- `promoted`: `true`

## Freshness Checks

### audit

- `ok`: `true`
- `missing_report_fingerprints`: `false`
- `mismatches`: `[]`

### verify

- `ok`: `true`
- `missing_report_fingerprints`: `false`
- `mismatches`: `[]`


## Consistency Checks

- `manifest_snapshot_present`: `true`
- `manifest_snapshot_matches`: `true`
- `mismatches`: `[]`

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
- `forge_status`: `promoted`
- `execution_skeleton`: `dataset_rank_then_attack`
- `audit_verdict`: `pass_with_review`
- `verify_verdict`: `pass_with_warnings`
- `promoted_at`: `2026-05-25T23:16:16.773089+00:00`

## Recommended Actions

- Attack artifacts are promoted into PromptMap runtime paths.
