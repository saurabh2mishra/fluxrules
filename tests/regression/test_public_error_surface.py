"""The error taxonomy is part of the public API and must stay reachable.

A caller that cannot *name* the exception it needs to handle has no way to
handle it except by catching ``Exception`` - which also swallows every bug in
their own code. Before this was pinned, none of the error types were exported
anywhere: handling a FluxRules failure meant importing from
``fluxrules.domain.errors``, an undocumented module path.

Two properties matter and neither is enforced by anything else:

* the names are importable from the documented locations, and
* the hierarchy holds, so ``except FluxRulesError`` really does catch them all.

``docs/reference/public-api.md`` documents both. These tests are what stop the
documentation from quietly becoming false.
"""

from __future__ import annotations

import pytest

#: Every publicly-documented error, with the base it must keep and the code it
#: must keep emitting. Codes appear in logs and API responses: messages may be
#: reworded freely, codes may not change.
PUBLIC_ERRORS = {
    "FluxRulesError": ("Exception", "FLUXRULES_ERROR"),
    "InvalidRuleError": ("FluxRulesError", "INVALID_RULE"),
    "UnknownOperatorError": ("FluxRulesError", "UNKNOWN_OPERATOR"),
    "CyclicDependencyError": ("FluxRulesError", "CYCLIC_DEPENDENCY"),
    "DSLValidationError": ("InvalidRuleError", "DSL_VALIDATION_ERROR"),
    "EmptyRuleLogicError": ("InvalidRuleError", "EMPTY_RULE_LOGIC"),
    "CorruptStoredRuleError": ("FluxRulesError", "CORRUPT_STORED_RULE"),
    "LossyConditionRebuildError": ("InvalidRuleError", "LOSSY_CONDITION_REBUILD"),
}


@pytest.mark.parametrize("name", sorted(PUBLIC_ERRORS))
def test_error_is_importable_from_the_package_root(name: str) -> None:
    import fluxrules

    assert hasattr(fluxrules, name), f"fluxrules.{name} is documented but missing"
    assert name in fluxrules.__all__


@pytest.mark.parametrize("name", sorted(PUBLIC_ERRORS))
def test_error_is_importable_from_the_domain_package(name: str) -> None:
    import fluxrules.domain as domain

    assert hasattr(domain, name)
    assert name in domain.__all__


@pytest.mark.parametrize("name", sorted(PUBLIC_ERRORS))
def test_every_export_is_the_same_class_object(name: str) -> None:
    """Re-exports must alias, not duplicate.

    Two classes sharing a name is worse than one being missing: ``except`` on
    the wrong one fails silently at runtime, and reads correctly in review.
    """
    import fluxrules
    import fluxrules.domain as domain
    import fluxrules.domain.errors as errors

    assert getattr(fluxrules, name) is getattr(errors, name)
    assert getattr(domain, name) is getattr(errors, name)


@pytest.mark.parametrize(("name", "expected"), sorted(PUBLIC_ERRORS.items()))
def test_hierarchy_and_code_are_stable(name: str, expected: tuple[str, str]) -> None:
    import fluxrules.domain.errors as errors

    base_name, code = expected
    cls = getattr(errors, name)

    assert cls.__mro__[1].__name__ == base_name
    assert cls.code == code


def test_one_except_clause_catches_the_whole_family() -> None:
    """The promise `public-api.md` makes to anyone writing error handling."""
    import fluxrules.domain.errors as errors
    from fluxrules import FluxRulesError

    for name in PUBLIC_ERRORS:
        cls = getattr(errors, name)
        with pytest.raises(FluxRulesError):
            raise cls("boom")


def test_dsl_validation_error_is_not_redefined_by_the_module_that_raises_it() -> None:
    """Regression: there were two distinct ``DSLValidationError`` classes.

    ``domain/errors.py`` and ``domain/dsl/validation.py`` each declared one.
    They shared a name and a code but not a base class, and only the latter was
    ever raised - so a caller doing ``except errors.DSLValidationError`` around
    ``validate_dsl()`` caught nothing, and the traceback named the class they
    thought they had handled.
    """
    from fluxrules.domain.dsl.validation import DSLValidationError as raised
    from fluxrules.domain.errors import DSLValidationError as canonical

    assert raised is canonical

    with pytest.raises(canonical):
        raise raised("boom")


def test_lossy_condition_view_warning_is_exported() -> None:
    """It is a warning, not an error - but callers still need to name it.

    Escalating it to an exception is the documented way to make a lossy read
    fail loudly, and that is impossible without an importable name.
    """
    import warnings

    import fluxrules
    from fluxrules import LossyConditionViewWarning

    assert "LossyConditionViewWarning" in fluxrules.__all__
    assert issubclass(LossyConditionViewWarning, UserWarning)

    with warnings.catch_warnings():
        warnings.simplefilter("error", LossyConditionViewWarning)
        with pytest.raises(LossyConditionViewWarning):
            warnings.warn("x", LossyConditionViewWarning, stacklevel=2)
