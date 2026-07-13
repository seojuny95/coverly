"""Conservative coverage-name matching for portfolio aggregation candidates."""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from app.services.coverage_knowledge.rules import (
    CoverageMatchingRules,
    apply_coverage_replacements,
    default_matching_rules,
    format_coverage_key,
    normalize_modifier,
    protected_terms_for,
)

_SPACES_PATTERN = re.compile(r"\s+")

MatchKind = Literal["exact", "curated_alias", "candidate", "distinct"]


@dataclass(frozen=True)
class CanonicalCoverageName:
    """Canonical identity plus the untouched source name for auditability."""

    original_name: str
    normalized_key: str
    display_name: str
    protected_terms: frozenset[str]
    alias_canonical: str | None


@dataclass(frozen=True)
class MatchDecision:
    kind: MatchKind
    mergeable: bool
    similarity: float
    left: CanonicalCoverageName
    right: CanonicalCoverageName
    reason: str


def canonicalize_coverage_name(
    name: str, rules: CoverageMatchingRules | None = None
) -> CanonicalCoverageName:
    """Return a deterministic identity without discarding the original name."""

    active_rules = rules or default_matching_rules()
    normalized_display = _normalize_unicode_and_spaces(name)
    without_wrapper = _unwrap_ignored_prefix_wrapper(
        normalized_display, active_rules.ignored_prefix_wrappers
    )
    without_ignored = _remove_ignored_parenthetical_segments(
        without_wrapper, active_rules.ignored_parenthetical_modifiers
    )
    replaced = apply_coverage_replacements(without_ignored, active_rules.replacements)
    normalized_key = format_coverage_key(replaced)
    alias_target = active_rules.alias_index.get(normalized_key)
    identity_key = alias_target.canonical_key if alias_target else normalized_key
    return CanonicalCoverageName(
        original_name=name,
        normalized_key=identity_key,
        display_name=alias_target.canonical_display if alias_target else _clean_display(replaced),
        protected_terms=protected_terms_for(identity_key, active_rules.protected_terms),
        alias_canonical=alias_target.canonical_key if alias_target else None,
    )


def match_coverage_names(
    left_name: str,
    right_name: str,
    rules: CoverageMatchingRules | None = None,
) -> MatchDecision:
    """Classify a pair; candidates are never automatically mergeable."""

    active_rules = rules or default_matching_rules()
    left = canonicalize_coverage_name(left_name, active_rules)
    right = canonicalize_coverage_name(right_name, active_rules)
    similarity = SequenceMatcher(None, left.normalized_key, right.normalized_key).ratio()
    if left.protected_terms != right.protected_terms:
        return _decision("distinct", False, similarity, left, right, "protected terms differ")
    if left.normalized_key == right.normalized_key:
        kind: MatchKind = (
            "curated_alias"
            if left.alias_canonical is not None or right.alias_canonical is not None
            else "exact"
        )
        return _decision(
            kind, True, similarity, left, right, "validated canonical identities match"
        )
    if similarity >= active_rules.candidate_similarity_threshold:
        return _decision(
            "candidate", False, similarity, left, right, "similar name requires review"
        )
    return _decision("distinct", False, similarity, left, right, "canonical identities differ")


def choose_display_name(names: Iterable[str], rules: CoverageMatchingRules | None = None) -> str:
    """Choose the shortest normal canonical display deterministically."""

    active_rules = rules or default_matching_rules()
    canonical_names = [canonicalize_coverage_name(name, active_rules) for name in names]
    if not canonical_names:
        raise ValueError("at least one coverage name is required")
    return min(
        (item.display_name for item in canonical_names),
        key=lambda display: (len(display), display),
    )


def query_contains_canonical_name(
    query: str,
    canonical_key: str,
    rules: CoverageMatchingRules | None = None,
) -> bool:
    """Match exact/curated substrings without promoting fuzzy candidates."""

    active_rules = rules or default_matching_rules()
    target = canonicalize_coverage_name(canonical_key, active_rules)
    query_key = format_coverage_key(
        apply_coverage_replacements(_normalize_unicode_and_spaces(query), active_rules.replacements)
    )
    aliases = {target.normalized_key}
    aliases.update(
        alias
        for alias, alias_target in active_rules.alias_index.items()
        if alias_target.canonical_key == target.normalized_key
    )
    for alias in sorted(aliases, key=len, reverse=True):
        start = query_key.find(alias)
        while start >= 0:
            end = start + len(alias)
            if not _has_overlapping_protected_difference(
                query_key, start, end, target.protected_terms, active_rules.protected_terms
            ):
                return True
            start = query_key.find(alias, start + 1)
    return False


def _decision(
    kind: MatchKind,
    mergeable: bool,
    similarity: float,
    left: CanonicalCoverageName,
    right: CanonicalCoverageName,
    reason: str,
) -> MatchDecision:
    return MatchDecision(kind, mergeable, similarity, left, right, reason)


def _normalize_unicode_and_spaces(value: str) -> str:
    return _SPACES_PATTERN.sub(" ", unicodedata.normalize("NFKC", value)).strip()


def _remove_ignored_parenthetical_segments(value: str, ignored_modifiers: frozenset[str]) -> str:
    segments = _top_level_parenthetical_segments(value)
    if segments is None:
        return value
    result: list[str] = []
    cursor = 0
    for start, end, content in segments:
        result.append(value[cursor:start])
        normalized_content = normalize_modifier(content)
        if normalized_content not in ignored_modifiers or "(" in content:
            result.append(value[start:end])
        cursor = end
    result.append(value[cursor:])
    return "".join(result)


def _unwrap_ignored_prefix_wrapper(value: str, ignored_wrappers: frozenset[str]) -> str:
    segments = _top_level_parenthetical_segments(value)
    if segments is None or len(segments) != 1:
        return value
    start, end, content = segments[0]
    wrapper = normalize_modifier(value[:start])
    if start == 0 or end != len(value) or wrapper not in ignored_wrappers:
        return value
    return content


def _top_level_parenthetical_segments(value: str) -> list[tuple[int, int, str]] | None:
    depth = 0
    start = 0
    segments: list[tuple[int, int, str]] = []
    for index, character in enumerate(value):
        if character == "(":
            if depth == 0:
                start = index
            depth += 1
        elif character == ")":
            depth -= 1
            if depth < 0:
                return None
            if depth == 0:
                segments.append((start, index + 1, value[start + 1 : index]))
    return segments if depth == 0 else None


def _clean_display(value: str) -> str:
    return _SPACES_PATTERN.sub(" ", value).strip(" -_/·")


def _has_overlapping_protected_difference(
    query: str,
    match_start: int,
    match_end: int,
    target_terms: frozenset[str],
    protected_terms: Sequence[str],
) -> bool:
    for term in protected_terms:
        if term in target_terms:
            continue
        start = query.find(term)
        while start >= 0:
            end = start + len(term)
            if start <= match_end and end >= match_start:
                return True
            start = query.find(term, start + 1)
    return False
