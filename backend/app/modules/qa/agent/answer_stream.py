"""Stream-item generator: validated response → meta → real-token deltas → completed.

This is the pure, testable sequence builder that Task 4c wires into the runtime.
It emits ``QaAgentMeta`` first, then answer ``QaAgentDelta`` items, then a final
``QaAgentCompleted``. For composable modes (grounded / general_guidance) it runs
the compose stream through the sentence-verify layer, so only verified sentences
reach the user and fabricated numbers are withheld. For fixed refusals
(insufficient / out_of_scope) the compose step must NOT run — the validated
answer is emitted verbatim as a single delta.
"""

import logging
from collections.abc import Iterator

from app.integrations.openai.client import TextStreamer
from app.modules.qa.agent.answer_spec import build_answer_spec
from app.modules.qa.agent.compose import compose_answer_stream
from app.modules.qa.agent.compose_stream import sentence_verified_deltas
from app.modules.qa.agent.contracts import (
    QaAgentCompleted,
    QaAgentDelta,
    QaAgentMeta,
    QaAgentStreamItem,
    RegisteredToolResult,
)
from app.modules.qa.schemas import PortfolioQuestionResponse

logger = logging.getLogger(__name__)

_COMPOSABLE = {"grounded", "general_guidance"}


def answer_stream_items(
    validated: PortfolioQuestionResponse,
    results: list[RegisteredToolResult],
    question: str,
    *,
    streamer: TextStreamer,
    compose: bool = True,
) -> Iterator[QaAgentStreamItem]:
    """Yield ``QaAgentMeta`` → ``QaAgentDelta``* (real-token sentences) →
    ``QaAgentCompleted``.

    Composable modes run compose streaming plus sentence verification to build
    deltas; fixed refusals emit ``validated.answer`` as a single delta without
    ever invoking compose. Callers that already hold a deterministic verbatim
    answer (guardrail tripwire fallbacks) pass ``compose=False`` to force the
    single-delta path and skip compose entirely.
    """

    yield QaAgentMeta(status=validated.status, generation=validated.generation)

    spec = build_answer_spec(validated, results)

    if compose and spec.mode in _COMPOSABLE:
        tokens = compose_answer_stream(spec, question, streamer=streamer)
        for sentence in sentence_verified_deltas(
            tokens, spec.amounts, list(spec.grounding_sources)
        ):
            yield QaAgentDelta(text=sentence)
    else:
        yield QaAgentDelta(text=validated.answer)

    yield QaAgentCompleted(response=validated)


def safe_answer_stream_items(
    validated: PortfolioQuestionResponse,
    results: list[RegisteredToolResult],
    question: str,
    *,
    streamer: TextStreamer,
    compose: bool = True,
) -> Iterator[QaAgentStreamItem]:
    """Wrap ``answer_stream_items`` so the stream always terminates.

    Compose or sentence verification may raise mid-stream. When it does, we log
    the exception type only (never PII) and degrade to the already-validated safe
    answer: if no delta reached the user yet, emit ``validated.answer`` as a
    single delta; then always emit a terminating ``QaAgentCompleted(validated)``.
    A broken stream is never disguised as a normal completion — the terminating
    item carries the safe ``validated`` response.

    The same degrade applies when compose runs to completion but sentence
    verification withholds every sentence (e.g. a model that only emits
    ungrounded numbers): rather than complete with zero deltas, we inject the
    validated answer as a single delta before the terminating
    ``QaAgentCompleted`` so the user is never left with a silently empty
    answer.
    """

    delta_emitted = False
    try:
        for item in answer_stream_items(
            validated, results, question, streamer=streamer, compose=compose
        ):
            if isinstance(item, QaAgentDelta):
                delta_emitted = True
            elif isinstance(item, QaAgentCompleted) and not delta_emitted:
                logger.warning(
                    "compose stream withheld all sentences; degraded to validated answer"
                )
                yield QaAgentDelta(text=validated.answer)
                delta_emitted = True
            yield item
    except Exception as exc:
        logger.warning("compose stream failed: %s", type(exc).__name__)
        if not delta_emitted:
            yield QaAgentDelta(text=validated.answer)
        yield QaAgentCompleted(response=validated)
        return
