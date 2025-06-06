# Single-Turn Orchestrator Attack.
async def single_turn_attack(orchestrator, prompts: list[str]):
    """
    Common processing for sending prompts and displaying conversations using Single-Turn Orchestrator.

    :param orchestrator: with orchestrator instance obtained with the statement
    :param prompts: List of prompts to send
    """
    try:
        await orchestrator.send_prompts_async(prompt_list=prompts)
        await orchestrator.print_conversations_async()
    except Exception as e:
        print(f"{e}")

# Single-Turn Orchestrator Attack for Jailbreak.
async def single_turn_jailbreak_attack(orchestrator):
    """
    Common processing for sending prompts and displaying conversations using Single-Turn Orchestrator.

    :param orchestrator: with orchestrator instance obtained with the statement
    """
    try:
        result = await orchestrator.execute_fuzzer()
        await result.print_templates_async()
        await result.print_conversations_async()
    except Exception as e:
        print(f"{e}")

# Multi-Turn Orchestrator Attack.
async def multi_turn_attack(orchestrator, prompt, memory_labels):
    """
        Common processing for sending prompts and displaying conversations using Multi-Turn Orchestrator.

        :param orchestrator: with orchestrator instance obtained with the statement
        :param prompt: a prompt to send
        :param memory_labels: a dictionary with categories keyed
        """
    try:
        result = await orchestrator.run_attack_async(objective=prompt, memory_labels=memory_labels)
        await result.print_conversation_async()
    except Exception as e:
        print(f"{e}")

async def run_single_turn_attack_sync(orchestrator, prompts: list[str]):
    """
    For calling from synchronous code.

    :param orchestrator: Instance of Orchestrator.
    :param prompts: Sending prompt list.
    """
    await single_turn_attack(orchestrator, prompts)

async def run_single_turn_jailbreak_attack_sync(orchestrator):
    """
    For calling from synchronous code.

    :param orchestrator: Instance of Orchestrator.
    """
    await single_turn_jailbreak_attack(orchestrator)

async def run_multi_turn_attack_sync(orchestrator, prompt, memory_labels):
    """
    For calling from synchronous code.

    :param orchestrator: Instance of Orchestrator.
    :param prompt: Sending prompt (str or list).
    :param memory_labels: Dictionary with categories keyed
    """
    await multi_turn_attack(orchestrator, prompt, memory_labels)
