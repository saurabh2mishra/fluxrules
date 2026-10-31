"""Every script in examples/ runs to completion.

Examples are documentation that users copy, but nothing exercised them, so a
behaviour change could leave one crashing unnoticed (25_nested_facts did). Each
script runs in its own process from a temporary copy of examples/, so anything
it writes (a SQLite database, for instance) stays out of the repository.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
EXAMPLES_DIR = REPO_ROOT / "examples"
SCRIPTS = sorted(EXAMPLES_DIR.glob("[0-9]*.py"))

# Generous: the slowest example finishes in about a second.
TIMEOUT_SECONDS = 120


@pytest.fixture(scope="module")
def examples_copy(tmp_path_factory: pytest.TempPathFactory) -> Path:
    target = tmp_path_factory.mktemp("examples") / "examples"
    shutil.copytree(
        EXAMPLES_DIR,
        target,
        ignore=shutil.ignore_patterns("__pycache__", "*.db"),
    )
    return target


def test_examples_are_found() -> None:
    assert len(SCRIPTS) >= 30


@pytest.mark.parametrize("script", SCRIPTS, ids=lambda path: path.name)
def test_example_runs(script: Path, examples_copy: Path, tmp_path: Path) -> None:
    env = {
        **os.environ,
        # Import fluxrules from this checkout, even without an installed copy.
        "PYTHONPATH": os.pathsep.join(
            filter(None, [str(REPO_ROOT / "src"), os.environ.get("PYTHONPATH")])
        ),
        # Keep a developer's own config files out of the run.
        "HOME": str(tmp_path),
    }
    env.pop("FLUXRULES_CONFIG_FILE", None)
    result = subprocess.run(  # noqa: S603 - runs this repository's own scripts
        [sys.executable, script.name],
        cwd=examples_copy,
        env=env,
        capture_output=True,
        text=True,
        timeout=TIMEOUT_SECONDS,
    )
    assert result.returncode == 0, (
        f"{script.name} exited with {result.returncode}\n"
        f"--- stderr (last 40 lines) ---\n" + "\n".join(result.stderr.splitlines()[-40:])
    )
