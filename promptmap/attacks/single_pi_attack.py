from uuid import uuid4

from engine.base_attack import BaseAttack
from engine.context import AttackContext
from engine.events import ProgressEvent, EVT_PROMPT, EVT_RESPONSE, EVT_SCORE, EVT_ACHIEVED, EVT_COMPLETE
from engine.models import AttackResult, Message

ATTACK_NAME = "Single_PI_Attack"


class SinglePIAttack(BaseAttack):
    """Send adversarial prompts directly to the target and score each response."""

    async def run(self, ctx: AttackContext, objective: str, **kwargs) -> AttackResult:
        conversation_id = str(uuid4())
        conversation: list[Message] = []

        converted = objective
        for converter in ctx.converters:
            converted = await converter.convert(converted)

        await ctx.emit(ProgressEvent(EVT_PROMPT, turn=1, data={"text": converted}))

        response = await ctx.target.send(converted, conversation_id)

        await ctx.emit(ProgressEvent(EVT_RESPONSE, turn=1, data={"text": response}))

        conversation.append(Message(role="user", content=converted))
        conversation.append(Message(role="assistant", content=response))

        score_result = await ctx.scorer.score(response, objective)

        await ctx.emit(ProgressEvent(EVT_SCORE, turn=1, data={
            "score": score_result.score,
            "achieved": score_result.achieved,
            "rationale": score_result.rationale,
        }))

        if score_result.achieved:
            await ctx.emit(ProgressEvent(EVT_ACHIEVED, turn=1, data={"score": score_result.score}))

        await ctx.emit(ProgressEvent(EVT_COMPLETE, data={
            "achieved": score_result.achieved,
            "score": score_result.score,
            "turns": 1,
        }))

        return AttackResult(
            attack_name=ATTACK_NAME,
            objective=objective,
            achieved=score_result.achieved,
            score=score_result.score,
            turns=1,
            conversation=conversation,
        )
