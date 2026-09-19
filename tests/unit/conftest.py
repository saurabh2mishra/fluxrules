"""
Configuration and fixtures for unit tests.

Unit tests are isolated, fast (<1s each), and don't require external dependencies.
"""

import pytest


def pytest_collection_modifyitems(items):
    """Automatically mark all tests in this directory as 'unit' if not already marked."""
    for item in items:
        if "unit" not in item.keywords:
            item.add_marker(pytest.mark.unit)
