"""
Configuration and fixtures for security tests.

Security tests check authorization, authentication, input validation,
and other security-related concerns.
"""

import pytest


def pytest_collection_modifyitems(items):
    """Automatically mark all tests in this directory as 'security' if not already marked."""
    for item in items:
        if "security" not in item.keywords:
            item.add_marker(pytest.mark.security)
