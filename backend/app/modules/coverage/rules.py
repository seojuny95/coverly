"""Load and validate data-driven coverage-name matching rules."""

import json
import re
import unicodedata
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import cast

from app.modules.reference_data.loader import load_reference_data
from app.modules.reference_data.paths import reference_data_path

_RULES_PATH = reference_data_path("coverage_matching_rules.json")
_FORMATTING_PATTERN = re.compile(r"[^0-9A-Za-z가-힣%~]")
_SPACES_PATTERN = re.compile(r"\s+")


@dataclass(frozen=True)
class AliasTarget:
    canonical_key: str
    canonical_display: str


@dataclass(frozen=True)
class CoverageMatchingRules:
    version: int
    candidate_similarity_threshold: float
    ignored_parenthetical_modifiers: frozenset[str]
    ignored_prefix_wrappers: frozenset[str]
    replacements: tuple[tuple[str, str], ...]
    alias_index: Mapping[str, AliasTarget]
    protected_terms: tuple[str, ...]


def load_matching_rules(path: Path = _RULES_PATH) -> CoverageMatchingRules:
    """Load a complete, internally consistent matching configuration."""

    payload = cast(object, json.loads(path.read_text(encoding="utf-8")))
    return _parse_matching_rules(payload)


def _parse_matching_rules(payload: object) -> CoverageMatchingRules:
    if not isinstance(payload, dict):
        raise ValueError("coverage matching rules must be an object")

    version = payload.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise ValueError("version must be a positive integer")

    threshold = payload.get("candidate_similarity_threshold")
    if not isinstance(threshold, int | float) or isinstance(threshold, bool):
        raise ValueError("candidate_similarity_threshold must be a number")
    if not 0 <= threshold <= 1:
        raise ValueError("candidate_similarity_threshold must be between 0 and 1")

    replacements = _validate_replacements(payload.get("replacements"))
    protected_terms = _validate_protected_terms(payload.get("protected_terms"), replacements)
    ignored_modifiers = _validate_ignored_modifiers(payload.get("ignored_parenthetical_modifiers"))
    ignored_wrappers = _validate_ignored_modifiers(payload.get("ignored_prefix_wrappers"))
    alias_index = _validate_alias_groups(payload.get("alias_groups"), replacements, protected_terms)
    return CoverageMatchingRules(
        version=version,
        candidate_similarity_threshold=float(threshold),
        ignored_parenthetical_modifiers=ignored_modifiers,
        ignored_prefix_wrappers=ignored_wrappers,
        replacements=replacements,
        alias_index=alias_index,
        protected_terms=protected_terms,
    )


@lru_cache(maxsize=1)
def default_matching_rules() -> CoverageMatchingRules:
    return load_reference_data("coverage_matching_rules", _RULES_PATH, _parse_matching_rules)


def format_coverage_key(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _FORMATTING_PATTERN.sub("", normalized).casefold()


def normalize_modifier(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    return _SPACES_PATTERN.sub("", normalized).casefold()


def apply_coverage_replacements(value: str, replacements: Sequence[tuple[str, str]]) -> str:
    result = value
    for source, target in replacements:
        result = result.replace(source, target)
    return result


def protected_terms_for(value: str, protected_terms: Sequence[str]) -> frozenset[str]:
    return frozenset(term for term in protected_terms if term in value)


def _validate_replacements(value: object) -> tuple[tuple[str, str], ...]:
    if not isinstance(value, dict):
        raise ValueError("replacements must be an object")

    replacements: list[tuple[str, str]] = []
    for source, target in value.items():
        if not isinstance(source, str) or not source:
            raise ValueError("replacement sources must be non-empty strings")
        if not isinstance(target, str) or not target:
            raise ValueError("replacement targets must be non-empty strings")
        if not format_coverage_key(source) or not format_coverage_key(target):
            raise ValueError("replacement values must contain identity characters")
        replacements.append((source, target))

    result = tuple(sorted(replacements, key=lambda item: (-len(item[0]), item[0])))
    _validate_replacement_graph(result)
    return result


def _validate_replacement_graph(replacements: Sequence[tuple[str, str]]) -> None:
    edges = {
        format_coverage_key(source): format_coverage_key(target) for source, target in replacements
    }
    if any(target in edges for target in edges.values()):
        raise ValueError("replacement chains or cycles are not allowed")


def _validate_protected_terms(
    value: object, replacements: Sequence[tuple[str, str]]
) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError("protected_terms must be a non-empty list")

    terms: set[str] = set()
    for term in value:
        if not isinstance(term, str) or not term:
            raise ValueError("protected terms must be non-empty strings")
        normalized = format_coverage_key(apply_coverage_replacements(term, replacements))
        if not normalized:
            raise ValueError("protected terms must contain identity characters")
        terms.add(normalized)
    return tuple(sorted(terms, key=lambda term: (-len(term), term)))


def _validate_ignored_modifiers(value: object) -> frozenset[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("ignored modifier collections must be non-empty lists")

    modifiers: set[str] = set()
    for modifier in value:
        if not isinstance(modifier, str) or not normalize_modifier(modifier):
            raise ValueError("ignored modifiers must be non-empty strings")
        modifiers.add(normalize_modifier(modifier))
    return frozenset(modifiers)


def _validate_alias_groups(
    value: object,
    replacements: Sequence[tuple[str, str]],
    protected_terms: Sequence[str],
) -> Mapping[str, AliasTarget]:
    if not isinstance(value, list):
        raise ValueError("alias_groups must be a list")

    aliases: dict[str, AliasTarget] = {}
    for group in value:
        canonical, members = _validated_alias_group(group)
        canonical_key = format_coverage_key(apply_coverage_replacements(canonical, replacements))
        canonical_terms = protected_terms_for(canonical_key, protected_terms)
        target = AliasTarget(canonical_key, canonical.strip())

        for member in [canonical, *members]:
            member_key = format_coverage_key(apply_coverage_replacements(member, replacements))
            if protected_terms_for(member_key, protected_terms) != canonical_terms:
                raise ValueError("alias protected terms must match canonical")
            existing = aliases.get(member_key)
            if existing is not None and existing.canonical_key != canonical_key:
                raise ValueError(f"alias belongs to multiple groups: {member}")
            aliases[member_key] = target
    return aliases


def _validated_alias_group(value: object) -> tuple[str, list[str]]:
    if not isinstance(value, dict):
        raise ValueError("each alias group must be an object")

    canonical = value.get("canonical")
    members = value.get("aliases")
    if not isinstance(canonical, str) or not canonical.strip():
        raise ValueError("alias canonical names must be non-empty strings")
    if not isinstance(members, list):
        raise ValueError("alias groups must contain an aliases list")
    if any(not isinstance(member, str) or not member for member in members):
        raise ValueError("aliases must be non-empty strings")
    if not format_coverage_key(canonical):
        raise ValueError("alias canonical names must contain identity characters")
    if any(not format_coverage_key(member) for member in members):
        raise ValueError("aliases must contain identity characters")
    return canonical, members
