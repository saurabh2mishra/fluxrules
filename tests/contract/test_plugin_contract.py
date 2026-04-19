from fluxrules.plugins.manager import PluginRegistry


def test_registry_can_register_extensions() -> None:
    registry = PluginRegistry()
    registry.register_rule_type("custom", object())
    registry.register_pipeline_step("audit", lambda payload: payload)
    assert "custom" in registry.rule_types
    assert "audit" in registry.pipeline_steps
