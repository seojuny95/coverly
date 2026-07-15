"""Official policy-change reference lookup from the configured Postgres database."""

from functools import lru_cache
from typing import Any, Protocol

import psycopg
from psycopg import sql
from psycopg.rows import dict_row

from app.schemas.analysis import PolicyChangeCheck, PolicyChangeSource
from app.settings import get_settings


class PolicyChangeRepository(Protocol):
    def list_active(self) -> tuple[PolicyChangeCheck, ...]: ...


class PostgresPolicyChangeRepository:
    def __init__(
        self,
        database_url: str,
        *,
        schema: str,
        change_table: str,
        source_table: str,
    ) -> None:
        self._database_url = database_url
        self._schema = schema
        self._change_table = change_table
        self._source_table = source_table

    def list_active(self) -> tuple[PolicyChangeCheck, ...]:
        query = sql.SQL(
            """
            SELECT
              c.title,
              c.summary,
              c.user_impact,
              c.effective_from,
              c.applies_to,
              c.related_tags,
              s.title AS source_title,
              s.publisher AS source_publisher,
              s.url AS source_url,
              s.published_at AS source_published_at,
              s.reliability AS source_reliability,
              s.caveat AS source_caveat
            FROM {change_table} c
            JOIN {source_table} s ON s.id = c.source_id
            WHERE c.active IS TRUE
            ORDER BY c.display_order ASC, c.effective_from DESC NULLS LAST
            """
        ).format(
            change_table=sql.Identifier(self._schema, self._change_table),
            source_table=sql.Identifier(self._schema, self._source_table),
        )
        with psycopg.connect(self._database_url, row_factory=dict_row) as connection:
            rows = connection.execute(query).fetchall()
        return tuple(_policy_change_from_row(row) for row in rows)


class NullPolicyChangeRepository:
    def list_active(self) -> tuple[PolicyChangeCheck, ...]:
        return ()


_preloaded_policy_changes: tuple[PolicyChangeCheck, ...] | None = None


def policy_changes_for_tags(tags: set[str], *, limit: int = 2) -> list[PolicyChangeCheck]:
    if not tags:
        return []

    changes = _preloaded_policy_changes
    if changes is None:
        try:
            changes = _cached_policy_changes()
        except Exception:
            return []

    matched = [change for change in changes if tags.intersection(change.related_tags)]
    return matched[:limit]


def warm_policy_change_cache() -> int:
    """Preload reference policy changes without making app startup depend on DB."""

    global _preloaded_policy_changes

    try:
        changes = _repository().list_active()
    except Exception:
        return 0

    _preloaded_policy_changes = changes
    return len(changes)


@lru_cache(maxsize=1)
def _cached_policy_changes() -> tuple[PolicyChangeCheck, ...]:
    return _repository().list_active()


@lru_cache(maxsize=1)
def _repository() -> PolicyChangeRepository:
    settings = get_settings()
    if not settings.database_url:
        return NullPolicyChangeRepository()
    return PostgresPolicyChangeRepository(
        settings.database_url,
        schema=settings.reference_schema,
        change_table=settings.policy_change_table,
        source_table=settings.reference_source_table,
    )


def _policy_change_from_row(row: dict[str, Any]) -> PolicyChangeCheck:
    publisher = str(row["source_publisher"] or "").strip()
    source_title = str(row["source_title"])
    label = f"{publisher} · {source_title}" if publisher else source_title
    change = PolicyChangeCheck(
        title=str(row["title"]),
        summary=str(row["summary"]),
        user_impact=str(row["user_impact"]),
        effective_from=str(row["effective_from"]) if row["effective_from"] is not None else None,
        applies_to=str(row["applies_to"]),
        related_tags=list(row["related_tags"] or ()),
        source=PolicyChangeSource(
            label=label,
            url=str(row["source_url"]),
            published_at=str(row["source_published_at"]),
            reliability=str(row["source_reliability"]),
            caveat=str(row["source_caveat"]),
        ),
    )
    return change
