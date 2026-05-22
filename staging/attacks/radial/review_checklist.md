# Review Checklist: Radial Attack

## Audit Summary

- `verdict`: `needs_refinement`
- `categories`: missing_algorithm_steps, unsafe_inference_detected, benchmark_not_advised

## Remaining Work

- `construct_responses` is `partial`: Response examples are preserved as metadata, but response-set construction is not executable.
- `collect_instructions` is `missing`: No implementation signal detected for this plan step.
- `calculate_probabilities` is `missing`: No implementation signal detected for this plan step.
- `score_instructions` is `missing`: No implementation signal detected for this plan step.
- `filter_instructions` is `missing`: No implementation signal detected for this plan step.
- `select_top_instructions` is `missing`: No implementation signal detected for this plan step.
- `splice_instructions` is `partial`: The draft supports prefix/suffix splicing, but still uses a generic baseline flow.
- Keep `supports_benchmark: false` until the audit findings are resolved.
- Add focused tests before promotion.
- Re-run `audit` after the next forge or manual refinement pass.

## Manual Review Prompts

- Does the runtime code actually execute each plan step, rather than only storing it in metadata?
- Are paper-specific assumptions exposed as parameters instead of hidden logic?
- Is the draft still relying on the generic forge baseline?
