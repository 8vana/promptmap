# Benchmark Notes: Radial Attack

## Initial Recommendation

- `supports_benchmark`: `false`
- Reason: generated scaffolds should be reviewed before being admitted to a standardized benchmark lane.

## Questions To Resolve

- Does the paper define a stable parameter set for repeated evaluation?
- Does the attack require hidden state, tool access, or environment assumptions that make benchmarking unstable?
- Should benchmark defaults differ from development defaults?
- Is the attack comparable across API-style and browser-style targets?

## Suggested Starting Defaults

```yaml
default_params: {num_affirmation_responses: 20, num_rejection_responses: 20, real_world_instructions_count: 30000,
  spliced_instructions_count: [2, 4], malicious_instruction_position: end}
benchmark_defaults: {}
```

## Notes

- Paper: Analyzing the Inherent Response Tendency of LLMs: Real-World Instructions-Driven Jailbreak
- URL: https://arxiv.org/abs/2312.04127
- Family: single_turn
