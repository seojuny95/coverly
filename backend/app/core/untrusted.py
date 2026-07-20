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

    escaped = _strip_fence_tags_to_fixed_point(text, label)
    return f"<{label}>\n{escaped.strip()}\n</{label}>"


def _strip_fence_tags_to_fixed_point(text: str, label: str) -> str:
    """Remove fence tags for `label`, repeating until nothing more matches.

    A single removal pass can splice the leftover characters around a match
    into a fresh tag (e.g. "</</문서>문서>" -> "</문서>" after one pass), so
    the attacker escapes the fence. Re-running the substitution to a fixed
    point closes that gap for any nesting depth. The string strictly shrinks
    on every pass that changes it (each match is replaced with nothing), so
    this terminates in at most len(text) iterations.
    """

    pattern = re.compile(rf"</?\s*{re.escape(label)}\s*>")
    previous = text
    while True:
        current = pattern.sub("", previous)
        if current == previous:
            return current
        previous = current


def strip_injection_markers(text: str) -> str:
    """Drop sentences that read as instructions. Single-line text only."""

    parts = _SENTENCE_SPLIT_RE.split(text.strip())
    kept = [part for part in parts if not any(marker in part for marker in _INJECTION_MARKERS)]
    return " ".join(kept).strip()


def strip_injection_markers_by_line(text: str) -> str:
    """Line-preserving variant, for composed multi-line blocks."""

    return "\n".join(strip_injection_markers(line) for line in text.split("\n"))
