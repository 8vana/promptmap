# Generation Notes: Radial E2E Attack

## Conservative Improvements Applied

- Added explicit `supports_benchmark = False` as required by rules
- Enhanced TODO comments with more specific context from the paper evidence
- Added docstring clarifications about paper-derived limitations
- Improved method documentation to reference specific paper concepts (Ta, Tr, Score = Ta - Tr)
- Preserved all existing uncertainties and ambiguities as explicit TODOs
- Maintained the same public contract and method signatures

## Skeleton

- `execution_skeleton`: `dataset_rank_then_attack`
- `family`: `single_turn`

## Step Mapping

- `construct_responses` -> `_build_response_templates` (todo-only)
- `collect_instructions` -> `_collect_candidate_instructions` (todo-only)
- `calculate_tendencies` -> `step::calculate_tendencies`
- `score_instructions` -> `_rank_candidate_instructions`
- `filter_instructions` -> `_filter_text_manipulation_instructions`
- `splice_instructions` -> `_build_attack_prompt`

## Preserved Ambiguities

- Planner MVP generated this draft heuristically; validate the attack flow against the paper.
- Default parameters are provisional unless the paper states them explicitly.
- Exact construction methodology for the 20 affirmation and 20 rejection responses not fully specified beyond examples
- Specific filtering criteria for text manipulation instructions not completely detailed
- Exact selection methodology for choosing which top-ranked instructions to use in splicing
- Complete prompt template structure not provided in paper excerpt
- Cross-language adaptation methodology for Chinese malicious instructions mentioned but not detailed in excerpt
- Benchmark recommendation was normalized to false in Phase A pending explicit human review.

## Key Implementation Details

- Response tendency calculation follows paper's Score = Ta - Tr formula concept
- Text manipulation filtering based on common patterns mentioned in paper
- Malicious instruction positioning supports "end" (default), "front", and "middle" as mentioned in paper
- Placeholder probability calculations pending actual LLM probability extraction implementation

## Repo Support

- No repo evidence recorded.

## Repo-Derived Hints

- No repo-derived defaults were promoted into `DEFAULT_PARAMS`.

## Divergences

- No divergences recorded.
