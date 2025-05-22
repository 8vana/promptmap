import pathlib

from pyrit.common.path import DATASETS_PATH
from pyrit.orchestrator import PromptSendingOrchestrator
from pyrit.score import SelfAskLikertScorer

from .attack_util import run_single_turn_attack_sync

TEST_ITEM_NAME = '(Single) Basic Prompt Injection'


async def run_attack(objective_target, prompts, scoring_target, converter_instances):
    """
    Orchestrate and run the prompt-based attack scenario using a custom web API endpoint.
    :param objective_target: An instance of CustomWebAPITarget.
    :param prompts: An iterable adversarial prompt of PromptSendingOrchestrator.
    :param scoring_target: An instance of OpenAIChatTarget.
    :param converter_instances: An instance of prompt converter.
    """
    try:
        # Define Scorer.
        harmfulness_scorer = SelfAskLikertScorer(
            chat_target=scoring_target,
            likert_scale_path=pathlib.Path(DATASETS_PATH) / "score" / "likert_scales" / "harm.yaml",

        )

        # Send adversarial prompts.
        orchestrator = PromptSendingOrchestrator(
            objective_target=objective_target,
            prompt_converters=converter_instances,
            scorers=[harmfulness_scorer],
            verbose=False
        )
        await run_single_turn_attack_sync(orchestrator, prompts)
    except Exception as e:
        print(f"{e}")

    print(f"[-] {TEST_ITEM_NAME} Attack completed successfully.")
