"""Every evaluation path gives the same answer for every comparison case.

``comparison_matrix`` evaluates each operator against each kind of value
(numbers, Decimal, booleans, strings, None, NaN, dates, lists, a missing
field), plain and wrapped in NOT, AND and OR, under each comparison setting.
It runs on the in-process paths, ``CrossFactEngine``, the CLI and the HTTP
API, and compares every path with ``engine, no prefilter``. A path is only
compared on the cases and facts it can express: ``CrossFactEngine`` has no
NOT or OR, and the CLI and HTTP API take JSON only.

Known disagreements are listed in ``comparison_matrix.KNOWN`` with the bug
behind them; the reference page shows the same list. The test
fails on a disagreement that is not listed, and on a listed one that no longer
happens, so the list stays exact: when a bug is fixed, remove its entry.
"""

from __future__ import annotations

import pytest
from tests.engine.comparison_matrix import (
    CONFIGS,
    KNOWN,
    PATHS,
    REFERENCE_PATH,
    Disagreement,
    MatrixResult,
    build_cases,
    build_facts,
    cli_path,
    http_path,
    run_matrix,
)


@pytest.fixture(scope="module")
def matrix(app, tmp_path_factory) -> MatrixResult:
    """Run the whole matrix once, including the CLI and HTTP API paths."""
    pytest.importorskip("fastapi")
    pytest.importorskip("typer")
    from fastapi.testclient import TestClient
    from tests.conftest import TestingSessionLocal, test_engine

    from fluxrules.api.database import Base, get_db

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)

    def _db():
        db = TestingSessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _db
    try:
        with TestClient(app) as client:
            return run_matrix(
                extra_paths=[
                    cli_path(tmp_path_factory.mktemp("cli")),
                    http_path(client, TestingSessionLocal),
                ]
            )
    finally:
        app.dependency_overrides.pop(get_db, None)
        Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="module")
def disagreements(matrix) -> list[Disagreement]:
    return matrix.disagreements


def test_the_matrix_covers_every_path_setting_and_operator():
    from fluxrules.engine.operators import VALID_OPERATORS

    cases, _ = build_cases()
    word_aliases = {"eq", "ne", "gt", "gte", "lt", "lte"}  # normalised to symbols first
    assert {c.op for c in cases} == VALID_OPERATORS - word_aliases
    assert REFERENCE_PATH in PATHS
    assert len(PATHS) >= 7 and len(CONFIGS) >= 6
    assert len(build_facts()) >= 19


def test_every_path_was_compared_under_every_setting(matrix):
    """No path silently skipped: each compared answers under each setting."""
    names = set(PATHS) | {"CLI", "HTTP API"}
    for name in names:
        for config in CONFIGS:
            assert matrix.compared.get((name, config), 0) > 0, (name, config)


def test_no_unlisted_disagreement(disagreements):
    unlisted = [d for d in disagreements if not any(k.matches(d) for k in KNOWN)]
    report = "\n".join(
        f"  [{d.config}] {d.path}: {d.case} on fact {d.fact}: reference={d.reference}, got={d.got}"
        for d in unlisted[:40]
    )
    assert not unlisted, f"{len(unlisted)} paths disagree with {REFERENCE_PATH!r}:\n{report}"


@pytest.mark.skipif(not KNOWN, reason="no known disagreements")
@pytest.mark.parametrize("known", KNOWN, ids=[k.title for k in KNOWN])
def test_every_listed_disagreement_still_happens(known, disagreements):
    assert any(known.matches(d) for d in disagreements), (
        "This disagreement no longer happens. Remove it from KNOWN: " + known.reason
    )
