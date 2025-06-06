from pyrit.orchestrator import FuzzerOrchestrator
from pyrit.prompt_converter import (
    FuzzerCrossOverConverter,
    FuzzerExpandConverter,
    FuzzerRephraseConverter,
    FuzzerShortenConverter,
    FuzzerSimilarConverter,
)

from .attack_util import run_single_turn_jailbreak_attack_sync

TEST_ITEM_NAME = '(Single) Fuzzing Jailbreak Attack'


async def run_attack(objective_target, prompts, jailbreak_templates, scoring_target, converter_target):
    """
    Orchestrate and run the prompt-based attack scenario using a custom web API endpoint.
    :param objective_target: An instance of CustomWebAPITarget.
    :param prompts: An iterable adversarial prompt of FuzzerOrchestrator.
    :param jailbreak_templates: An iterable jailbreak templates of FuzzerOrchestrator.
    :param scoring_target: An instance of OpenAIChatTarget.
    :param converter_target: An instance of OpenAIChatTarget.
    """
    try:
        # Define Fuzzer.
        fuzzer_converters = [
            FuzzerShortenConverter(converter_target=converter_target),
            FuzzerExpandConverter(converter_target=converter_target),
            FuzzerRephraseConverter(converter_target=converter_target),
            FuzzerSimilarConverter(converter_target=converter_target),
            FuzzerCrossOverConverter(converter_target=converter_target),
        ]

        # Send adversarial prompts.
        orchestrator = FuzzerOrchestrator(
            prompts=prompts,
            prompt_target=objective_target,
            prompt_templates=jailbreak_templates,
            scoring_target=scoring_target,
            target_jailbreak_goal_count=1,
            template_converters=fuzzer_converters,
            verbose=False
        )
        await run_single_turn_jailbreak_attack_sync(orchestrator)
        orchestrator.dispose_db_engine()
    except Exception as e:
        print(f"{e}")

    print(f"[-] {TEST_ITEM_NAME} Attack completed successfully.")
