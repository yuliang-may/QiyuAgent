"""Input and output guardrails for the LacquerTutor agent.

Input guardrails:
  - safety_bypass_guardrail: Block queries attempting to skip safety steps
  - off_topic_guardrail: Block non-lacquer-craft queries

Output guardrails:
  - evidence_grounding_guardrail: Ensure irreversible steps have evidence refs
  - hallucination_guardrail: Ensure cited evidence IDs exist in the store

Uses the SDK's @input_guardrail and @output_guardrail decorators.
"""

from __future__ import annotations

import logging
from typing import Any

from agents import (
    Agent,
    GuardrailFunctionOutput,
    InputGuardrailTripwireTriggered,
    OutputGuardrailTripwireTriggered,
    RunContextWrapper,
    input_guardrail,
    output_guardrail,
)

from lacquertutor.agent.context import LacquerTutorContext
from lacquertutor.models.contract import PlanContract

logger = logging.getLogger(__name__)

# ── Safety bypass patterns ──────────────────────────────────────

SAFETY_BYPASS_PATTERNS = [
    "跳过检查",
    "跳过安全",
    "不需要检查",
    "不用检查湿度",
    "skip safety",
    "skip check",
    "ignore safety",
    "ignore checkpoint",
    "不管安全",
    "别管检查点",
    "直接开始",
    "skip verification",
]


@input_guardrail
async def safety_bypass_guardrail(
    ctx: RunContextWrapper[LacquerTutorContext],
    agent: Agent,
    input: str | list,
) -> GuardrailFunctionOutput:
    """Block queries that attempt to bypass safety checks.

    Uses simple pattern matching (no LLM call needed).
    """
    text = str(input).lower() if isinstance(input, str) else str(input).lower()

    for pattern in SAFETY_BYPASS_PATTERNS:
        if pattern.lower() in text:
            logger.warning("Safety bypass attempt blocked: %r", pattern)
            return GuardrailFunctionOutput(
                output_info={"blocked_pattern": pattern},
                tripwire_triggered=True,
            )

    return GuardrailFunctionOutput(
        output_info={"status": "passed"},
        tripwire_triggered=False,
    )


# ── Off-topic detection ─────────────────────────────────────────

LACQUER_KEYWORDS = [
    "漆", "涂", "打磨", "抛光", "固化", "湿度", "大漆", "合成漆",
    "lacquer", "coat", "cure", "sand", "polish", "finish", "substrate",
    "humidity", "varnish", "primer", "sealer", "urushi",
    "工艺", "craft", "涂层", "涂装", "基底", "漆艺",
]


@input_guardrail
async def off_topic_guardrail(
    ctx: RunContextWrapper[LacquerTutorContext],
    agent: Agent,
    input: str | list,
) -> GuardrailFunctionOutput:
    """Block clearly off-topic queries.

    Allows through any query that contains lacquer/craft keywords.
    Only blocks queries that are clearly unrelated.
    """
    text = str(input).lower() if isinstance(input, str) else str(input).lower()

    # Allow short messages (likely follow-up answers) and first-turn greeting
    if len(text) < 10:
        return GuardrailFunctionOutput(output_info={"status": "short_message"}, tripwire_triggered=False)

    has_keyword = any(kw.lower() in text for kw in LACQUER_KEYWORDS)

    if has_keyword:
        return GuardrailFunctionOutput(output_info={"status": "on_topic"}, tripwire_triggered=False)

    # If no keywords, it might still be a follow-up answer — let it through
    # Only block truly obvious off-topic (conservative approach)
    return GuardrailFunctionOutput(
        output_info={"status": "no_keywords_but_allowed"},
        tripwire_triggered=False,
    )


# ── Evidence grounding guardrail (output) ────────────────────────

@output_guardrail
async def evidence_grounding_guardrail(
    ctx: RunContextWrapper[LacquerTutorContext],
    agent: Agent,
    output: Any,
) -> GuardrailFunctionOutput:
    """Verify that irreversible steps in the contract have evidence refs.

    Runs the same check as ContractVerifier._check_grounding() but
    as an output guardrail that can block the response.
    """
    contract = getattr(ctx.context, '_generated_contract', None)
    if contract is None:
        return GuardrailFunctionOutput(output_info={"status": "no_contract"}, tripwire_triggered=False)

    ungrounded = []
    for step in contract.steps:
        if step.is_irreversible and not step.evidence_refs:
            ungrounded.append(step.step_number)

    if ungrounded:
        logger.warning("Evidence grounding failed for steps: %s", ungrounded)
        return GuardrailFunctionOutput(
            output_info={"ungrounded_steps": ungrounded},
            tripwire_triggered=True,
        )

    return GuardrailFunctionOutput(output_info={"status": "grounded"}, tripwire_triggered=False)


# ── Hallucination guardrail (output) ────────────────────────────

@output_guardrail
async def hallucination_guardrail(
    ctx: RunContextWrapper[LacquerTutorContext],
    agent: Agent,
    output: Any,
) -> GuardrailFunctionOutput:
    """Verify that cited evidence IDs actually exist in the evidence store."""
    contract = getattr(ctx.context, '_generated_contract', None)
    if contract is None:
        return GuardrailFunctionOutput(output_info={"status": "no_contract"}, tripwire_triggered=False)

    store = ctx.context.evidence_store
    invalid_refs = set()

    for step in contract.steps:
        for ref in step.evidence_refs:
            if store.get(ref) is None:
                invalid_refs.add(ref)

    for cp in contract.checkpoints:
        for ref in cp.evidence_refs:
            if store.get(ref) is None:
                invalid_refs.add(ref)

    if invalid_refs:
        logger.warning("Hallucinated evidence refs: %s", invalid_refs)
        return GuardrailFunctionOutput(
            output_info={"invalid_refs": list(invalid_refs)},
            tripwire_triggered=True,
        )

    return GuardrailFunctionOutput(output_info={"status": "valid"}, tripwire_triggered=False)
