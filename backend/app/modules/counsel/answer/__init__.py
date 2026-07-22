"""Turning a planned turn into the streamed answer the user sees.

The stages run in order: executor resolves the planned fact tasks against the
pure fact modules, composer renders them, escalation decides whether they can
stand as the answer, and stream emits the SSE events.
"""

from app.modules.counsel.answer.stream import build_answer_stream
from app.modules.qa.events import (
    CounselDeltaEvent,
    CounselEndEvent,
    CounselMetaEvent,
    CounselStreamEvent,
    serialize_event,
)

__all__ = [
    "CounselDeltaEvent",
    "CounselEndEvent",
    "CounselMetaEvent",
    "CounselStreamEvent",
    "build_answer_stream",
    "serialize_event",
]
