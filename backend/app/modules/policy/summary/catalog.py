"""Catalog-backed insurer aliases and evidence matching."""

import re
from functools import lru_cache

from app.core.grounding import wording_grounded
from app.modules.reference_data import load_database_reference_data

_INSURER_NAME_SUFFIXES = (
    "화재해상보험",
    "해상화재보험",
    "손해보험",
    "생명보험",
    "화재보험",
    "해상보험",
    "화재",
    "생명",
    "보험",
)
_BRAND_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+|[가-힣]+")


@lru_cache
def get_insurer_candidates() -> tuple[str, ...]:
    return load_database_reference_data("insurer_catalog", _validate_insurer_candidates)


def _validate_insurer_candidates(payload: object) -> tuple[str, ...]:
    if not isinstance(payload, list):
        raise ValueError("insurer catalog must be a JSON list")

    candidates = tuple(value for value in payload if isinstance(value, str) and value.strip())
    if not candidates:
        raise ValueError("insurer catalog must contain at least one insurer")

    return candidates


@lru_cache
def get_insurer_aliases() -> dict[str, tuple[str, ...]]:
    """Generate catalog-derived insurer aliases used by local extraction."""

    aliases: dict[str, set[str]] = {
        insurer: set(_generated_insurer_aliases(insurer)) for insurer in get_insurer_candidates()
    }
    return {insurer: tuple(values) for insurer, values in aliases.items() if values}


@lru_cache
def get_insurer_contact_evidence() -> tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...]:
    """Return catalog insurers with official homepage domains and call-center digits."""

    payload = load_database_reference_data("claim_channels", _validate_contact_data)
    entries = payload["보험사"]

    evidence: list[tuple[str, tuple[str, ...], tuple[str, ...]]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        insurer_name = entry.get("보험사")
        if not isinstance(insurer_name, str):
            continue

        insurer = _catalog_insurer_for_name(insurer_name)
        if insurer is None:
            continue

        domains = tuple(
            value
            for key in ("홈페이지", "청구링크", "source")
            if isinstance(entry.get(key), str)
            for value in _domain_evidence(entry[key])
        )
        phone = entry.get("고객센터")
        phones = (re.sub(r"\D", "", phone),) if isinstance(phone, str) else ()
        evidence.append((insurer, domains, tuple(value for value in phones if value)))

    return tuple(evidence)


def match_insurer_from_text(text: str) -> str | None:
    """Return the catalog insurer whose alias or contact evidence appears in text."""

    contact_match = _match_insurer_by_contact_evidence(text)
    if contact_match:
        return contact_match

    normalized_text = _normalize_insurer_alias(text)
    if not normalized_text:
        return None

    for insurer, aliases in get_insurer_aliases().items():
        if any(_insurer_alias_matches(alias, text, normalized_text) for alias in aliases):
            return insurer
    return None


def insurer_name_is_grounded(candidate: str, text: str) -> bool:
    """Check catalog insurer grounding against its document-visible brand tokens."""

    brand = candidate
    for suffix in _INSURER_NAME_SUFFIXES:
        if brand.endswith(suffix) and len(brand) > len(suffix):
            brand = brand[: -len(suffix)]
            break

    tokens = [token for token in _BRAND_TOKEN_PATTERN.findall(brand) if len(token) >= 2]
    if not tokens:
        return wording_grounded(candidate, text)

    normalized_text = re.sub(r"\s", "", text).lower()
    return all(token.lower() in normalized_text for token in tokens)


def _match_insurer_by_contact_evidence(text: str) -> str | None:
    normalized_text = _normalize_contact_text(text)
    digits = re.sub(r"\D", "", text)
    for insurer, domains, phones in get_insurer_contact_evidence():
        if domains and any(domain in normalized_text for domain in domains):
            return insurer
        if phones and any(phone in digits for phone in phones):
            return insurer
    return None


def _normalize_insurer_alias(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value).casefold()


def _normalize_contact_text(value: str) -> str:
    return re.sub(r"\s+", "", value).casefold()


def _insurer_alias_matches(alias: str, text: str, normalized_text: str) -> bool:
    normalized_alias = _normalize_insurer_alias(alias)
    if not normalized_alias:
        return False
    if len(normalized_alias) <= 2:
        tokens = {token.casefold() for token in _BRAND_TOKEN_PATTERN.findall(text)}
        return normalized_alias in tokens
    return normalized_alias in normalized_text


def _validate_contact_data(payload: object) -> dict[str, list[object]]:
    if not isinstance(payload, dict):
        raise ValueError("claim channels must be an object")

    entries = payload.get("보험사")
    if not isinstance(entries, list):
        raise ValueError("claim channels must contain an insurer list")
    return {"보험사": entries}


def _domain_evidence(url: str) -> tuple[str, ...]:
    match = re.search(r"https?://([^/\s]+)", url.casefold())
    if not match:
        return ()
    host = match.group(1).removeprefix("www.")
    return (host,) if "." in host else ()


def _catalog_insurer_for_name(value: str) -> str | None:
    if value in get_insurer_candidates():
        return value

    normalized_value = _normalize_insurer_alias(value)
    if not normalized_value:
        return None

    for insurer, aliases in get_insurer_aliases().items():
        normalized_aliases = {_normalize_insurer_alias(alias) for alias in aliases}
        if normalized_value in normalized_aliases:
            return insurer
    return None


def _generated_insurer_aliases(insurer: str) -> tuple[str, ...]:
    """Generate generic aliases from catalog names without insurer-specific code."""

    generated = {insurer}
    for suffix in _INSURER_NAME_SUFFIXES:
        if insurer.endswith(suffix) and len(insurer) > len(suffix):
            generated.add(insurer[: -len(suffix)])

    brand = min(generated, key=len)
    if brand.endswith("손해") and len(brand) > len("손해"):
        generated.add(f"{brand.removesuffix('손해')}손보")

    return tuple(alias for alias in generated if len(alias.strip()) >= 2)
