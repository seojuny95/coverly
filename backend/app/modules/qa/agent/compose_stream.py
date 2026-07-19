"""Sentence-level verify-and-release assembler for the compose token stream.

Safety boundary: the compose LLM streams an answer token by token, writing
confirmed numbers as ``{{label}}`` placeholders. This module sits between the
raw token stream and the user. It buffers tokens into whole sentences (one
sentence behind, so a decimal point or a placeholder split across tokens is
never mistaken for a boundary), substitutes placeholders from the confirmed
``amounts`` map, and re-verifies every remaining raw number against the
grounding sources. Only fully verified sentences are yielded.

Fail-closed is the rule: an unknown placeholder label, a leftover brace, or any
raw number that is not grounded withholds the whole sentence. When in doubt the
sentence is dropped, never emitted unverified.
"""

import re
from collections.abc import Iterator

from app.modules.qa.agent.grounding import numeric_claims_grounded_in_sources

# Hard sentence terminators: their presence always ends a sentence. A period is
# handled separately because "3.5" is a decimal, not a boundary.
_HARD_TERMINATORS = frozenset("!?。\n")
_PLACEHOLDER = re.compile(r"\{\{([^{}]*)\}\}")
# Every maximal digit run (grouped thousands and decimals included). The compose
# model writes all confirmed amounts as placeholders, so any digit surviving
# substitution is suspect and must match a whole digit run from the sources
# (token-set membership, not a substring search — see _residual_digits_grounded).
_DIGIT_RUN = re.compile(r"\d[\d,]*(?:\.\d+)?")


def sentence_verified_deltas(
    tokens: Iterator[str],
    amounts: dict[str, str],
    grounding_sources: list[str],
) -> Iterator[str]:
    """Buffer tokens into sentences, substitute ``{{label}}`` with confirmed
    amounts, verify remaining raw numbers, and yield only verified sentences.

    Buffers one sentence behind so placeholders spanning token boundaries and
    decimal points are resolved before a sentence is cut and checked.
    """

    buffer = ""

    for token in tokens:
        buffer += token
        while True:
            end = _boundary_end(buffer, stream_ended=False)
            if end is None:
                break
            sentence, buffer = buffer[:end], buffer[end:]
            verified = _verify_sentence(sentence, amounts, grounding_sources)
            if verified is not None:
                yield verified

    # Flush: at stream end an ambiguous trailing period is a real boundary, and
    # any remaining text without a terminator is a final sentence.
    while buffer:
        end = _boundary_end(buffer, stream_ended=True)
        if end is None:
            end = len(buffer)
        sentence, buffer = buffer[:end], buffer[end:]
        verified = _verify_sentence(sentence, amounts, grounding_sources)
        if verified is not None:
            yield verified


def _boundary_end(buffer: str, *, stream_ended: bool) -> int | None:
    """Return the exclusive end index of the first complete sentence in
    ``buffer`` (including its terminator), or ``None`` if no boundary is
    confirmed yet.

    A period ends a sentence unless it is a decimal point (digit on both
    sides). A period that is the last character and follows a digit is
    ambiguous mid-stream (more digits may follow), so we wait unless the stream
    has ended.
    """

    for index, char in enumerate(buffer):
        if char in _HARD_TERMINATORS:
            return index + 1
        if char != ".":
            continue

        prev_is_digit = index > 0 and buffer[index - 1].isdigit()
        next_char = buffer[index + 1] if index + 1 < len(buffer) else None

        if next_char is None:
            if prev_is_digit and not stream_ended:
                return None  # possible decimal in progress — wait for more
            return index + 1
        if prev_is_digit and next_char.isdigit():
            continue  # decimal point, not a boundary
        return index + 1

    return None


def _verify_sentence(
    sentence: str,
    amounts: dict[str, str],
    grounding_sources: list[str],
) -> str | None:
    """Substitute placeholders and verify raw numbers. Return the released
    sentence, or ``None`` to withhold it (fail-closed)."""

    substituted = _substitute_placeholders(sentence, amounts)
    if substituted is None:
        return None  # unknown label or malformed placeholder — withhold

    sources = [*amounts.values(), *grounding_sources]
    if not numeric_claims_grounded_in_sources(substituted, sources, ()):
        return None  # a raw number is not grounded — withhold

    if not _residual_digits_grounded(substituted, sources):
        return None  # a digit run (any/no unit) is absent from sources — withhold

    return substituted


def _residual_digits_grounded(sentence: str, sources: list[str]) -> bool:
    """Belt-and-suspenders guard: every digit run left after placeholder
    substitution must match a whole digit run present in the sources.

    ``numeric_claims_grounded_in_sources`` only recognizes Korean money and a
    fixed counter list, so numbers with other units (5000달러, 9999명) or none
    (bare 9,999) escape it. Here every maximal digit run is matched against
    the set of digit runs found in the sources (token-set membership, not
    substring search) — a raw substring check would let a fabricated 3000
    through against a grounded 30,000,000, or 3.5 through against 13.5, or
    let two adjacent sources glue into a fabricated run. Sources are joined
    with a space to keep runs from different sources from merging. Placeholder
    values (in ``amounts.values()``) and quoted numbers (in
    ``grounding_sources``) are part of ``sources`` and pass. Comparison is
    done on comma/space-stripped forms so 9,999 == 9999."""

    source_runs = {_strip_separators(m.group()) for m in _DIGIT_RUN.finditer(" ".join(sources))}
    return all(_strip_separators(m.group()) in source_runs for m in _DIGIT_RUN.finditer(sentence))


def _strip_separators(text: str) -> str:
    return re.sub(r"[\s,]", "", text)


def _substitute_placeholders(sentence: str, amounts: dict[str, str]) -> str | None:
    """Replace every ``{{label}}`` with its confirmed amount. Return ``None`` if
    any label is unknown or a stray brace remains after substitution."""

    unknown = False

    def replace(match: re.Match[str]) -> str:
        nonlocal unknown
        label = match.group(1)
        if label not in amounts:
            unknown = True
            return match.group(0)
        return amounts[label]

    substituted = _PLACEHOLDER.sub(replace, sentence)
    if unknown:
        return None
    if "{" in substituted or "}" in substituted:
        return None  # malformed / partial placeholder — fail-closed

    return substituted
