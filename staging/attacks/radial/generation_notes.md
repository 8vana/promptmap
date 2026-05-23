# Generation Notes: Radial Attack

## Skeleton

- `execution_skeleton`: `dataset_rank_then_attack`
- `family`: `single_turn`

## Step Mapping

- `construct_responses` -> `_build_response_templates` (todo-only)
- `collect_instructions` -> `_collect_candidate_instructions` (todo-only)
- `calculate_probabilities` -> `_calculate_response_tendencies` (todo-only)
- `score_instructions` -> `_rank_candidate_instructions`
- `filter_instructions` -> `_filter_text_manipulation_instructions`
- `select_top_instructions` -> `_select_top_instructions`
- `splice_instructions` -> `_build_attack_prompt`

## Preserved Ambiguities

- Planner MVP generated this draft heuristically; validate the attack flow against the paper.
- Default parameters are provisional unless the paper states them explicitly.
- Mathematical formulas for calculating probabilities and scores are not decoded in the excerpt
- Specific affirmation and rejection response templates are referenced in App. A but not provided
- Exact number of top-ranked instructions to select is not specified
- Specific criteria for filtering text manipulation instructions beyond examples
- Implementation details for probability extraction from LLMs
- Evaluation results table appears truncated
- Benchmark recommendation was normalized to false in Phase A pending explicit human review.

## Repo Support

- No repo evidence recorded.

## Repo-Derived Hints

- No repo-derived defaults were promoted into `DEFAULT_PARAMS`.

## Divergences

- No divergences recorded.
