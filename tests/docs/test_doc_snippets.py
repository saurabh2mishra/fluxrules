"""Check 2 - documented Python snippets execute.

Broader but noisier than the import check. Two design points from the plan
matter enormously here:

* **Multi-block continuity.** Blocks within a page routinely build on each
  other (a class defined in block 4 is used in block 15). Blocks are therefore
  accumulated into *one shared namespace per page*, executed in document order.
  Executing them in isolation produces ~120 false failures.
* **Sandboxed cwd.** Snippets that write ``.db`` files must not pollute the repo.

Parametrised per file so a failure names the offending page.
"""

from __future__ import annotations

import ast
import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy.orm import sessionmaker

from tests.docs._extract import extract_code_blocks, markdown_files


def _page_ids() -> list[Path]:
    return markdown_files()


#: Environment variables that steer every persistence entry point at the
#: sandbox database. Relative SQLite URLs resolve against the *current* cwd,
#: which the harness rewrites per page - absolute URLs remove that hazard.
_DB_ENV_VARS = (
    "FLUXRULES_DB_URL",
    "FLUXRULES_DEV_DB_URL",
    "DATABASE_URL",
)


@pytest.fixture()
def doc_sandbox_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Give a page an isolated, fully migrated SQLite database.

    Snippets that persist rules previously failed with ``sqlite I/O`` because
    they connected to a *relative* URL created under a different cwd, against a
    file whose tables had never been created. Three things fix that for good:

    1. an **absolute** URL, so cwd changes can never re-point the connection;
    2. a **reset singleton**, so no engine leaks in from an earlier page;
    3. an **explicit schema creation**, so the tables exist before first use.
    """
    from fluxrules.persistence import DatabaseConfig, DBConnectionManager

    db_path = tmp_path / "doc_snippets.db"
    url = f"sqlite:///{db_path}"
    for var in _DB_ENV_VARS:
        monkeypatch.setenv(var, url)
    monkeypatch.setenv("FLUXRULES_ENV", "dev")

    DBConnectionManager.reset()
    manager = DBConnectionManager.initialize(DatabaseConfig.from_env())
    manager.create_all_tables()

    # ``fluxrules.api.database`` builds its engine at *import* time, so setting
    # the environment is not enough once another test has already imported it.
    # Rebind the module globals for the duration of the page.
    import fluxrules.api.database as api_db
    import fluxrules.api.models  # noqa: F401  (register ORM tables on Base)

    api_engine = api_db._build_engine(url)
    api_db.Base.metadata.create_all(bind=api_engine)
    monkeypatch.setattr(api_db, "engine", api_engine)
    monkeypatch.setattr(
        api_db,
        "SessionLocal",
        sessionmaker(autocommit=False, autoflush=False, bind=api_engine),
    )

    try:
        yield db_path
    finally:
        api_engine.dispose()
        DBConnectionManager.reset()


def _seed_namespace(block, namespace: dict[str, object], rel: str) -> None:
    """Best-effort: run only the *import* lines of a non-executable block.

    Skipped blocks are excluded from assertions, but their imports still define
    names that later, genuinely-executable blocks depend on. Executing the
    whole block is not an option - it is skipped precisely because it cannot
    run (missing file, deliberately-invalid example). Importing alone is
    side-effect-light and enough to keep the page's namespace continuous.
    """
    try:
        tree = ast.parse(block.source)
    except SyntaxError:
        return  # deliberately-invalid example; nothing to harvest
    for node in tree.body:
        if not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        try:
            exec(
                compile(ast.Module([node], []), f"{rel}:{block.line}", "exec"),
                namespace,
            )
        except Exception:
            pass  # an unimportable name simply stays undefined


@pytest.mark.parametrize("path", _page_ids(), ids=lambda p: p.name)
def test_doc_snippets_execute(path: Path, tmp_path: Path, doc_sandbox_db: Path, request) -> None:
    """Execute a page's Python blocks in one shared, sandboxed namespace."""
    all_python = [b for b in extract_code_blocks(path) if b.is_python]
    blocks = [b for b in all_python if not b.is_skipped]
    if not blocks:
        pytest.skip("no executable python blocks")

    rel = all_python[0].rel
    namespace: dict[str, object] = {"__name__": "__doc_snippet__"}

    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        for block in all_python:
            if block.is_skipped:
                # A skipped block is still part of the page's narrative, and
                # frequently carries the imports that later blocks rely on
                # (e.g. a `python skip` block that needs a file on disk but
                # opens with `from fluxrules import PhreakEngine`). Dropping it
                # entirely makes valid downstream blocks fail with cascading
                # NameErrors that no reader would ever hit. Harvest what we can
                # and ignore the failure - the block is not under test.
                _seed_namespace(block, namespace, rel)
                continue
            try:
                exec(compile(block.source, f"{rel}:{block.line}", "exec"), namespace)
            except Exception as exc:
                pytest.fail(f"{rel}:{block.line} failed to execute: {type(exc).__name__}: {exc}")
    finally:
        os.chdir(cwd)
