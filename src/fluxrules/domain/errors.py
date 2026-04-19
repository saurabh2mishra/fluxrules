"""Domain-specific error taxonomy with stable symbolic codes."""


class FluxRulesError(Exception):
    code = "FLUXRULES_ERROR"


class InvalidRuleError(FluxRulesError):
    code = "INVALID_RULE"


class UnknownOperatorError(FluxRulesError):
    code = "UNKNOWN_OPERATOR"
