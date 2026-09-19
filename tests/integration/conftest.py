"""
Configuration and fixtures for integration tests.

Integration tests involve external services (DB, API, Redis), are slower (1-5s each),
but must be isolated and reproducible.
"""

import pytest


def pytest_collection_modifyitems(items):
    """Automatically mark all tests in this directory as 'integration' if not already marked."""
    for item in items:
        if "integration" not in item.keywords:
            item.add_marker(pytest.mark.integration)
