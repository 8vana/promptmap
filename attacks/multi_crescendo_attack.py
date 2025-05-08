from pyrit.orchestrator import CrescendoOrchestrator

from .attack_util import run_multi_turn_attack_sync

TEST_ITEM_NAME = '(Multi) Crescendo Attack'


async def run_attack(objective_target, prompts, adversarial_target, scoring_target):
    """
    Orchestrate and run the prompt-based attack scenario using a custom web API endpoint.
    :param objective_target: An instance of CustomWebAPITarget.
    :param prompts: A list of prompt strings.
    :param adversarial_target: An instance of OpenAIChatTarget for Adversarial.
    :param scoring_target: An instance of OpenAIChatTarget for Scoring.
    """
    try:
        orchestrator = CrescendoOrchestrator(
            objective_target=objective_target,
            adversarial_chat=adversarial_target,
            max_turns=10,
            max_backtracks=5,
            scoring_target=scoring_target,
            prompt_converters=[],
            verbose=True
        )
        await run_multi_turn_attack_sync(orchestrator, prompts, memory_labels={"harm_category": "illegal"})
    except Exception as e:
        print(f"{e}")

    print(f"[-] {TEST_ITEM_NAME} Attack completed successfully.")
