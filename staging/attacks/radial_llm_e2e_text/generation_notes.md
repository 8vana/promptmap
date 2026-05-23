# Generation Notes: Radial LLM E2E Text Attack

## Skeleton

- `execution_skeleton`: `dataset_rank_then_attack`
- `family`: `single_turn`

## Step Mapping

- `1` -> `step::1`
- `2` -> `step::2`
- `3` -> `step::3`
- `4` -> `step::4`
- `5` -> `step::5`
- `6` -> `step::6`
- `7` -> `step::7`

## Preserved Ambiguities

- Planner MVP generated this draft heuristically; validate the attack flow against the paper.
- Default parameters are provisional unless the paper states them explicitly.
- Complete list of 40 manual responses referenced in App. A not provided
- Mathematical formulas for probability calculations not fully decoded in excerpt
- Specific selection criteria for top-ranked instructions not detailed
- Exact splicing format and template structure not specified
- Cross-language attack methodology mentioned but not detailed
- Benchmark recommendation was normalized to false in Phase A pending explicit human review.

## Repo Support

- No repo evidence recorded.

## Repo-Derived Hints

- No repo-derived defaults were promoted into `DEFAULT_PARAMS`.

## Divergences

- No divergences recorded.

## Forge Backend Notes

- LLM forge fallback triggered after error: ReadTimeoutError: Read timeout on endpoint URL: "https://bedrock-runtime.us-west-2.amazonaws.com/model/us.anthropic.claude-sonnet-4-20250514-v1%3A0/converse"
