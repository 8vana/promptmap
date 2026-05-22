# Review Checklist: Radial Attack

- Confirm the paper metadata is correct.
- Confirm `attack_id`, `module_name`, `class_name`, and `registered_name` match the intended naming convention.
- Replace the baseline placeholder flow in `attack_module.py` with the paper's real algorithm.
- Check whether the attack is truly `single_turn` and whether that family maps cleanly to PromptMap runtime expectations.
- Validate required dependencies:
  - `scorer_llm`
- Validate target assumptions:
  - `api`
  - `stateless`
- Confirm whether the attack should remain `prompt_technique_aware: false`.
- Confirm benchmark suitability before changing `supports_benchmark`.
- Add tests before promotion.
- Run catalog and dataset validation after promotion.
