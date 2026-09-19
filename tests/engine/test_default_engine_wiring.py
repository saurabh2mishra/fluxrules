from fluxrules.api.engines.adapter import APIEngineAdapter
from fluxrules.core import RuleEngine
from fluxrules.engine import get_engine
from fluxrules.engine.phreak import PhreakEngine


def test_get_engine_default_is_phreak():
    engine = get_engine()
    assert isinstance(engine, PhreakEngine)


def test_core_ruleengine_alias_is_phreak():
    assert RuleEngine is PhreakEngine


def test_api_adapter_default_engine_type_is_phreak():
    adapter = APIEngineAdapter(enable_cache=False, enable_metrics=False)
    assert adapter._engine_type == "PHREAK"
    assert isinstance(adapter._engine, PhreakEngine)
