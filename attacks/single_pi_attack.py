import pathlib

from pyrit.common.path import DATASETS_PATH
from pyrit.models import SeedPromptDataset
from pyrit.orchestrator import PromptSendingOrchestrator
from pyrit.score import SelfAskLikertScorer
from pyrit.prompt_converter import UrlConverter

from .attack_util import run_single_turn_attack_sync

TEST_ITEM_NAME = '(Single) Basic Prompt Injection'


async def run_attack(objective_target, scoring_target):
    """
    Orchestrate and run the prompt-based attack scenario using a custom web API endpoint.
    :param objective_target: An instance of CustomWebAPITarget.
    :param scoring_target: An instance of OpenAIChatTarget.
    """
    try:
        # Define test prompts.
        seed_prompt_dataset = SeedPromptDataset.from_yaml_file(
            pathlib.Path(DATASETS_PATH) / "seed_prompts" / "illegal.prompt"
        )
        prompts = [seed_prompt.value for seed_prompt in seed_prompt_dataset.prompts]

        # Define Scorer.
        harmfulness_scorer = SelfAskLikertScorer(
            chat_target=scoring_target,
            likert_scale_path=pathlib.Path(DATASETS_PATH) / "score" / "likert_scales" / "harm.yaml",

        )

        # Send adversarial prompts.
        orchestrator = PromptSendingOrchestrator(
                objective_target=objective_target,
                prompt_converters=[UrlConverter()],
                scorers=[harmfulness_scorer]
        )
        await run_single_turn_attack_sync(orchestrator, prompts)
    except Exception as e:
        print(f"{e}")

    print(f"[-] {TEST_ITEM_NAME} Attack completed successfully.")
