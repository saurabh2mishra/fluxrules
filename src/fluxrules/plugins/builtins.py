"""Built-in extension registration points."""


def register_builtins(registry) -> None:
    registry.register_rule_type("default", object())
