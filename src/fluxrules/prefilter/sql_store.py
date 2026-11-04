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

Soundness: the query may keep extra facts but must never drop one the engine
would fire on. Each field has two columns: its value when that value is a number
SQL compares exactly as Python does (an ``int`` within 2**53, a ``float`` or a
``bool``), and whether the field is present at all. A range or equality check
excludes a row only when the field is absent, or when its number fails the
check; a present value that is not such a number (text, a ``Decimal``, a date, a
huge ``int``) always keeps its row, because Python might still compare it. A
rule value that is not such a number is never used to exclude rows.

The original fact is stored as JSON, with ``Decimal``, dates, times, tuples and
sets tagged so they come back exactly as they went in.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
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

        Each field gets an indexed ``Float`` column holding its value when it is
        an exactly comparable number (NULL otherwise), and an ``Integer``
        presence column (1 when the fact has the field). A JSON payload column
        preserves the exact original fact for engine evaluation.
        """
        self._fields = sorted(set(fields))
        self._metadata = MetaData()
        columns: list[Column[Any]] = [
            Column(_PK, Integer, primary_key=True, autoincrement=True),
            Column(_PAYLOAD, String, nullable=False),
        ]
        for f in self._fields:
            columns.append(Column(_col(f), Float, nullable=True, index=True))
            columns.append(Column(_present_col(f), Integer, nullable=False))
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
        row: dict[str, Any] = {_PAYLOAD: encode_fact(fact)}
        for f in self._fields:
            v = fact.get(f)
            # A boolean fact is never screened out: under strict_type_comparison
            # the engine cannot order it against a number, and must see it to
            # report that. The rule side still screens numbers with True / False.
            row[_col(f)] = None if isinstance(v, bool) else _sql_number(v)
            row[_present_col(f)] = 1 if f in fact else 0
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
                yield decode_fact(payload)

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
            present = self._table.c.get(_present_col(fld))
            if col is None or present is None:
                return None
            op, val = pred.op, pred.value
            if op == "__exists__":
                parts.append(present == 1)
                continue
            if op not in _SQL_OPS or _sql_number(val) is None:
                # Only an exactly comparable number can exclude rows soundly;
                # anything else leaves the clause unbounded.
                return None
            check = _SQL_OPS[op](col, _sql_number(val))
            # A present value with no exact number (text, Decimal, a date, a
            # huge int) may still compare in Python: keep its row.
            parts.append(or_(check, and_(present == 1, col.is_(None))))
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


def _present_col(field: str) -> str:
    """The column that records whether a fact has *field*."""
    return "p_" + field


_SQL_OPS = {
    ">": lambda col, v: col > v,
    ">=": lambda col, v: col >= v,
    "<": lambda col, v: col < v,
    "<=": lambda col, v: col <= v,
    "==": lambda col, v: col == v,
}

# Beyond this an int has no exact float, so SQL would compare a rounded value.
_EXACT_INT = 2**53


def _sql_number(value: Any) -> float | None:
    """*value* as a float SQL compares exactly as Python does, or ``None``.

    A ``bool`` counts, as Python compares it as 0 or 1. A ``Decimal``, an int
    beyond 2**53 and NaN do not: their SQL comparison could differ from
    Python's, so the row is kept for the engine to decide.
    """
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int):
        return float(value) if -_EXACT_INT <= value <= _EXACT_INT else None
    if isinstance(value, float):
        return None if math.isnan(value) else value
    return None


# --- lossless JSON for the stored fact ---------------------------------------

_TAG = "__fluxrules_type__"


def _tagged(value: Any, path: str) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return {_TAG: "decimal", "v": str(value)}
    if isinstance(value, datetime):
        return {_TAG: "datetime", "v": value.isoformat()}
    if isinstance(value, date):
        return {_TAG: "date", "v": value.isoformat()}
    if isinstance(value, time):
        return {_TAG: "time", "v": value.isoformat()}
    if isinstance(value, list):
        return [_tagged(v, f"{path}[{i}]") for i, v in enumerate(value)]
    if isinstance(value, tuple):
        return {_TAG: "tuple", "v": [_tagged(v, f"{path}[{i}]") for i, v in enumerate(value)]}
    if isinstance(value, (set, frozenset)):
        kind = "frozenset" if isinstance(value, frozenset) else "set"
        return {_TAG: kind, "v": [_tagged(v, f"{path}[]") for v in value]}
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(
                    f"fact field {path!r} has a non-string key {key!r}; the prefilter "
                    "store can only save string keys"
                )
            out[key] = _tagged(item, f"{path}.{key}")
        if _TAG in value:
            return {_TAG: "dict", "v": out}
        return out
    raise TypeError(
        f"fact field {path!r} holds a {type(value).__name__}, which the prefilter store "
        "cannot save. Convert it to a number, string, Decimal, date or list first."
    )


def _untagged(value: Any) -> Any:
    if isinstance(value, list):
        return [_untagged(v) for v in value]
    if not isinstance(value, dict):
        return value
    kind = value.get(_TAG)
    if kind is None:
        return {k: _untagged(v) for k, v in value.items()}
    inner = value["v"]
    if kind == "decimal":
        return Decimal(inner)
    if kind == "datetime":
        return datetime.fromisoformat(inner)
    if kind == "date":
        return date.fromisoformat(inner)
    if kind == "time":
        return time.fromisoformat(inner)
    if kind == "tuple":
        return tuple(_untagged(v) for v in inner)
    if kind == "set":
        return {_untagged(v) for v in inner}
    if kind == "frozenset":
        return frozenset(_untagged(v) for v in inner)
    if kind == "dict":
        return {k: _untagged(v) for k, v in inner.items()}
    raise ValueError(f"unknown stored value type {kind!r}")


def encode_fact(fact: dict[str, Any]) -> str:
    """Serialise *fact* so :func:`decode_fact` returns an equal fact.

    Raises:
        TypeError: For a value the store cannot save, naming its field.
    """
    for key in fact:
        if not isinstance(key, str):
            raise TypeError(
                f"fact has a non-string field name {key!r}; the prefilter store can "
                "only save string field names"
            )
    return json.dumps({key: _tagged(value, key) for key, value in fact.items()})


def decode_fact(payload: str) -> dict[str, Any]:
    """The fact :func:`encode_fact` stored."""
    return {key: _untagged(value) for key, value in json.loads(payload).items()}
