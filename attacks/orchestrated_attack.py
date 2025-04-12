import pathlib

from pyrit.common.path import DATASETS_PATH
from pyrit.models import SeedPromptDataset
from pyrit.orchestrator import PromptSendingOrchestrator
from pyrit.prompt_converter import UrlConverter

TEST_ITEM_NAME = 'Basic Prompt Injection'


async def run_attack(target):
    """
    Orchestrate and run the prompt-based attack scenario using a custom web API endpoint.
    :param target: An instance of CustomWebAPITarget.
    """
    try:
        # Loading data set (illegal.prompt).
        seed_prompt_dataset = SeedPromptDataset.from_yaml_file(
            pathlib.Path(DATASETS_PATH) / "seed_prompts" / "illegal.prompt"
        )
        prompts = [seed_prompt.value for seed_prompt in seed_prompt_dataset.prompts]

        with PromptSendingOrchestrator(objective_target=target,
                                       prompt_converters=[UrlConverter()]) as orchestrator:
            await orchestrator.send_prompts_async(prompt_list=prompts)
            await orchestrator.print_conversations()
    except Exception as e:
        print(f"{e}")

    print("[-] Basic Prompt Injection Attack completed successfully.")
