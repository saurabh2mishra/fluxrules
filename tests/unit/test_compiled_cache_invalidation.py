"""Regression tests for compiled-cache invalidation wiring.

The naming refactor left two lazy imports pointing at the removed
``fluxrules.validation._compiled_cache`` path. Both were wrapped in
``except ImportError``, so the failure was silent: the compiled-condition cache
was never invalidated after rule edits, risking stale rule evaluation. These
tests pin the canonical import path (``fluxrules.services.validation._compiled_cache``)
and prove each invalidation path actually calls through to it.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from fluxrules.api.routes import rules as rules_route
from fluxrules.api.services import rule_service
from fluxrules.services.validation import _compiled_cache


def test_rule_service_compiled_cache_import_resolves() -> None:
    # Import must resolve at module load -> availability flag is True and the
    # bound symbol is the real invalidate() from the canonical module.
    assert rule_service.COMPILED_CACHE_AVAILABLE is True
    assert rule_service._invalidate_compiled_cache is _compiled_cache.invalidate


def test_invalidate_rule_cache_calls_compiled_cache(monkeypatch) -> None:
    spy = MagicMock()
    monkeypatch.setattr(rule_service, "_invalidate_compiled_cache", spy)

    rule_service.invalidate_rule_cache(group="payments")

    spy.assert_called_once_with("payments")


def test_invalidate_conflict_cache_calls_compiled_cache(monkeypatch) -> None:
    # The route helper lazily imports the compiled cache; patching the canonical
    # module's invalidate proves the lazy import resolves to it (no ImportError).
    spy = MagicMock()
    monkeypatch.setattr(_compiled_cache, "invalidate", spy)

    class _FakeAdapter:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def reload_rules(self) -> None:
            pass

    monkeypatch.setattr(rules_route, "APIEngineAdapter", _FakeAdapter)

    rules_route.invalidate_conflict_cache(db=MagicMock())

    spy.assert_called_once_with()
