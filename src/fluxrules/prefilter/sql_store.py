"""Indexed fact store for pre-filtering (SQLite Dev / PostgreSQL Prod).

Backend-agnostic via SQLAlchemy Core. The backend is chosen by the existing
``fluxrules.persistence.database_config.DatabaseConfig`` env switch:

    dev   -> sqlite:///fluxrules_dev.db        (zero infra)
    prod  -> postgresql+psycopg://...          (FLUXRULES_DB_URL)

Schema strategy: a **wide columnar** table (one column per referenced field) with
a B-tree index on each field that appears in a pre-filter predicate. This is the
fast path for fixed-schema fact streams (e.g. ``field_0 .. field_N``). The
candidate query is a sound DNF: ``OR`` of per-rule ``AND`` constraints, so it
returns exactly the facts that could satisfy *some* rule's necessary conditions.

Soundness: a field constraint is only used to exclude a row when the predicate is
*range* or *equality* on a present value. ``NULL`` (absent field) handling matches
the engine: a row is excluded by ``field > 5`` if ``field IS NULL`` (engine also
returns False for absent fields). Equality clauses likewise require non-NULL.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from sqlalchemy import (
    Column,
    Float,
    Integer,
    MetaData,
    String,
    Table,
    and_,
    create_engine,
    insert,
    or_,
    select,
    text,
)
from sqlalchemy.engine import Engine

from fluxrules.persistence.database_config import DatabaseConfig
from fluxrules.prefilter.predicate import PredicateSet, RuleClause

logger = logging.getLogger(__name__)

_PK = "__fact_id__"
_PAYLOAD = "__payload__"


@dataclass
class LoadStats:
    """Metrics from a bulk load."""

    facts_loaded: int = 0
    fields_indexed: int = 0


class FactPreFilterStore:
    """Indexed, backend-agnostic fact store used to pre-screen facts.

    Usage::

        store = FactPreFilterStore()              # dev -> SQLite
        store.ensure_schema(predicate_set.fields)
        store.bulk_load(facts)
        for fact in store.candidates(predicate_set):
            engine.evaluate(fact)
    """

    def __init__(
        self,
        config: DatabaseConfig | None = None,
        *,
        engine: Engine | None = None,
        table_name: str = "prefilter_facts",
    ) -> None:
        self._config = config or DatabaseConfig.from_env()
        self._engine: Engine = engine or create_engine(self._config.db_url, future=True)
        self._table_name = table_name
        self._metadata = MetaData()
        self._table: Table | None = None
        self._fields: list[str] = []

    @property
    def dialect(self) -> str:
        return self._engine.dialect.name

    # schema

    def ensure_schema(self, fields: Iterable[str]) -> None:
        """(Re)create the fact table with one column per field + indexes.

        Numeric values dominate rule conditions, so each field is stored as a
        ``Float`` column (NULL when absent). A raw JSON payload column preserves
        the *exact* original fact so non-numeric / extra keys survive round-trip
        for engine evaluation.
        """
        self._fields = sorted(set(fields))
        self._metadata = MetaData()
        columns: list[Column[Any]] = [
            Column(_PK, Integer, primary_key=True, autoincrement=True),
            Column(_PAYLOAD, String, nullable=False),
        ]
        for f in self._fields:
            columns.append(Column(_col(f), Float, nullable=True, index=True))
        self._table = Table(self._table_name, self._metadata, *columns)

        with self._engine.begin() as conn:
            self._table.drop(conn, checkfirst=True)
            if self.dialect == "sqlite":
                conn.execute(text("PRAGMA journal_mode=WAL"))
                conn.execute(text("PRAGMA synchronous=OFF"))
            self._metadata.create_all(conn)
        logger.info(
            "prefilter schema ready: %s cols, %d indexed fields (%s)",
            len(columns),
            len(self._fields),
            self.dialect,
        )

    # load

    def bulk_load(self, facts: Iterable[dict[str, Any]], batch_size: int = 5_000) -> LoadStats:
        """Insert facts in batches. Returns load statistics."""
        assert self._table is not None, "call ensure_schema() before bulk_load()"
        stats = LoadStats(fields_indexed=len(self._fields))
        batch: list[dict[str, Any]] = []
        with self._engine.begin() as conn:
            for fact in facts:
                batch.append(self._row(fact))
                if len(batch) >= batch_size:
                    conn.execute(insert(self._table), batch)
                    stats.facts_loaded += len(batch)
                    batch.clear()
            if batch:
                conn.execute(insert(self._table), batch)
                stats.facts_loaded += len(batch)
        logger.info("prefilter loaded %d facts", stats.facts_loaded)
        return stats

    def _row(self, fact: dict[str, Any]) -> dict[str, Any]:
        row: dict[str, Any] = {_PAYLOAD: json.dumps(fact)}
        for f in self._fields:
            v = fact.get(f)
            row[_col(f)] = v if _is_number(v) else None
        return row

    # query

    def candidates(self, predicates: PredicateSet) -> Iterator[dict[str, Any]]:
        """Yield original facts that could match some rule (sound superset).

        If any rule is unfilterable (NOT / custom predicate / non-numeric), the
        store conservatively returns *all* facts - still sound, just no speedup
        for that portion.
        """
        assert self._table is not None, "call ensure_schema() before candidates()"
        stmt = select(self._table.c[_PAYLOAD])

        where = self._build_where(predicates)
        if where is not None:
            stmt = stmt.where(where)

        with self._engine.connect() as conn:
            result = conn.execution_options(stream_results=True).execute(stmt)
            for (payload,) in result:
                yield json.loads(payload)

    def _build_where(self, predicates: PredicateSet):
        """Build a sound DNF WHERE clause, or ``None`` to mean 'return all'."""
        if predicates.has_unfilterable_rule:
            # At least one rule cannot be bounded -> any fact may match it.
            return None
        clause_exprs = []
        for clause in predicates.filterable_clauses:
            expr = self._clause_expr(clause)
            if expr is None:
                return None  # safety: unbounded clause -> return all
            clause_exprs.append(expr)
        if not clause_exprs:
            return None
        return or_(*clause_exprs)

    def _clause_expr(self, clause: RuleClause):
        assert self._table is not None
        parts = []
        for fld, pred in clause.must.items():
            col = self._table.c.get(_col(fld))
            if col is None:
                return None
            op, val = pred.op, pred.value
            if op == "__exists__":
                parts.append(col.isnot(None))
            elif op == ">":
                parts.append(col > val)
            elif op == ">=":
                parts.append(col >= val)
            elif op == "<":
                parts.append(col < val)
            elif op == "<=":
                parts.append(col <= val)
            elif op == "==":
                if _is_number(val):
                    parts.append(col == val)
                else:
                    # Non-numeric equality isn't stored in the numeric column;
                    # cannot filter soundly -> treat clause as unbounded.
                    return None
            else:
                return None
        if not parts:
            return None
        return and_(*parts)

    # lifecycle

    def count(self) -> int:
        assert self._table is not None
        with self._engine.connect() as conn:
            return int(
                conn.execute(select(text("count(*)")).select_from(self._table)).scalar() or 0
            )

    def dispose(self) -> None:
        self._engine.dispose()


def _col(field: str) -> str:
    """Map a fact field name to a safe column name."""
    return "f_" + field


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)
