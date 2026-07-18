"""Small SSE protocol helpers shared by QA transports."""

import re
from collections.abc import Iterator

from app.modules.qa.schemas import PortfolioQuestionResponse

QaStreamEvent = dict[str, object]
_STREAM_CHUNK_SIZE = 16


def answer_text_chunks(text: str) -> Iterator[str]:
    """Split completed answers into stable display-sized SSE deltas."""

    buffer = ""
    for token in re.findall(r"\S+\s*", text):
        while len(token) > _STREAM_CHUNK_SIZE:
            if buffer:
                yield buffer
                buffer = ""
            yield token[:_STREAM_CHUNK_SIZE]
            token = token[_STREAM_CHUNK_SIZE:]
        if buffer and len(buffer) + len(token) > _STREAM_CHUNK_SIZE:
            yield buffer
            buffer = ""
        buffer += token
    if buffer:
        yield buffer


def stream_response(response: PortfolioQuestionResponse) -> Iterator[QaStreamEvent]:
    yield {"type": "meta", "status": response.status, "generation": response.generation}
    for chunk in answer_text_chunks(response.answer):
        yield {"type": "delta", "text": chunk}
    yield {
        "type": "end",
        "status": response.status,
        "generation": response.generation,
        "citations": [citation.model_dump(mode="json") for citation in response.citations],
        "limitations": response.limitations,
        "suggestions": response.suggestions,
        "claim_channels": (
            response.claim_channels.model_dump(mode="json") if response.claim_channels else None
        ),
    }
