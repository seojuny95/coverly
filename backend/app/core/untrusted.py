"""Frame untrusted document text so a model reads it as data, not instructions.

Uploaded policy PDFs are third-party files: a sentence inside one can read as an
instruction to the model. These helpers mark the trust boundary explicitly.
"""

import re

_INJECTION_MARKERS = (
    "이전 지시",
    "시스템 지시",
    "지시를 무시",
    "답하라",
    "출력하라",
    "추천하라",
    "권유하라",
)

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def wrap_untrusted(text: str, *, label: str = "문서") -> str:
    """Fence untrusted text, stripping any embedded tag that would break out."""

    escaped = re.sub(rf"</?\s*{re.escape(label)}\s*>", "", text)
    return f"<{label}>\n{escaped.strip()}\n</{label}>"


def strip_injection_markers(text: str) -> str:
    """Drop sentences that read as instructions. Single-line text only."""

    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    kept = [part for part in parts if not any(marker in part for marker in _INJECTION_MARKERS)]
    return " ".join(kept).strip()


def strip_injection_markers_by_line(text: str) -> str:
    """Line-preserving variant, for composed multi-line blocks."""

    return "\n".join(strip_injection_markers(line) for line in text.split("\n"))
