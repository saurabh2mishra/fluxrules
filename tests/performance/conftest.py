"""
Configuration and fixtures for performance tests.

Performance tests are benchmarks, stress tests, and scalability tests.
These are intentionally slow (5-30s each) and should be deselected in fast CI runs.
Run with: pytest tests/performance -v

Or exclude from regular test runs:
    pytest tests/ -m "not performance"
"""

import pathlib

import pytest

_PERF_DIR = pathlib.Path(__file__).parent


def pytest_collection_modifyitems(items):
    """Auto-mark tests located in this directory as 'performance'.

    Although this conftest lives in ``tests/performance/``, pytest invokes
    ``pytest_collection_modifyitems`` once per session and passes it every
    collected item. We therefore restrict marking to items whose file lives
    under this directory so that ``-m "not performance"`` still selects the
    rest of the suite.
    """
    for item in items:
        item_path = pathlib.Path(str(item.fspath))
        if item_path.parent == _PERF_DIR or _PERF_DIR in item_path.parents:
            if "performance" not in item.keywords:
                item.add_marker(pytest.mark.performance)
