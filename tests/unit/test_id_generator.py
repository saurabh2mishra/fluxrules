"""Tests for the unified RuleIDGenerator and DeploymentConfig."""

from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

import pytest

from fluxrules.config.deployment import (
    ConfigValidationError,
    DeploymentConfig,
    DeploymentType,
)
from fluxrules.utils.id_generators import IDStrategy, RuleIDGenerator

# RuleIDGenerator - basic usage


class TestRuleIDGeneratorBasic:
    """Core functionality of RuleIDGenerator."""

    def test_default_is_sequential(self):
        gen = RuleIDGenerator()
        assert gen.strategy is IDStrategy.SEQUENTIAL
        assert gen.next_id() == 1
        assert gen.next_id() == 2

    def test_sequential_start(self):
        gen = RuleIDGenerator(start=100)
        assert gen.next_id() == 100

    def test_sequential_reset(self):
        gen = RuleIDGenerator()
        gen.next_id()
        gen.next_id()
        gen.reset()
        assert gen.next_id() == 1

    def test_uuid_strategy(self):
        gen = RuleIDGenerator(strategy="uuid")
        uid = gen.next_id()
        assert isinstance(uid, str)
        assert len(uid) == 36  # UUID format

    def test_uuid_unique(self):
        gen = RuleIDGenerator(strategy="uuid")
        ids = {gen.next_id() for _ in range(100)}
        assert len(ids) == 100

    def test_snowflake_strategy(self):
        gen = RuleIDGenerator(strategy="snowflake", machine_id=1)
        sid = gen.next_id()
        assert isinstance(sid, int)
        assert sid > 0

    def test_snowflake_unique(self):
        gen = RuleIDGenerator(strategy="snowflake", machine_id=0)
        ids = [gen.next_id() for _ in range(1000)]
        assert len(set(ids)) == 1000

    def test_snowflake_monotonic(self):
        gen = RuleIDGenerator(strategy="snowflake", machine_id=0)
        ids = [gen.next_id() for _ in range(100)]
        assert ids == sorted(ids)

    def test_snowflake_invalid_machine_id(self):
        with pytest.raises(ValueError):
            RuleIDGenerator(strategy="snowflake", machine_id=9999)

    def test_hash_based_strategy(self):
        gen = RuleIDGenerator(strategy="hash_based")
        h = gen.next_id(name="rule_1", content="age > 18")
        assert isinstance(h, int)
        assert h > 0

    def test_hash_based_deterministic(self):
        gen = RuleIDGenerator(strategy="hash_based")
        a = gen.next_id(name="rule_1", content="age > 18")
        b = gen.next_id(name="rule_1", content="age > 18")
        assert a == b

    def test_hash_based_different(self):
        gen = RuleIDGenerator(strategy="hash_based")
        a = gen.next_id(name="rule_1", content="age > 18")
        b = gen.next_id(name="rule_2", content="age > 21")
        assert a != b

    def test_hybrid_strategy(self):
        gen = RuleIDGenerator(strategy="hybrid", instance_id=1)
        hid = gen.next_id()
        assert isinstance(hid, int)
        assert hid > 0

    def test_hybrid_different_instances(self):
        g1 = RuleIDGenerator(strategy="hybrid", instance_id=0)
        g2 = RuleIDGenerator(strategy="hybrid", instance_id=1)
        ids1 = {g1.next_id() for _ in range(100)}
        ids2 = {g2.next_id() for _ in range(100)}
        assert ids1.isdisjoint(ids2)

    def test_strategy_from_string(self):
        gen = RuleIDGenerator(strategy="sequential")
        assert gen.strategy is IDStrategy.SEQUENTIAL

    def test_strategy_from_enum(self):
        gen = RuleIDGenerator(strategy=IDStrategy.UUID)
        assert gen.strategy is IDStrategy.UUID

    def test_invalid_strategy(self):
        with pytest.raises(ValueError):
            RuleIDGenerator(strategy="invalid_strategy")

    def test_repr(self):
        gen = RuleIDGenerator()
        assert "sequential" in repr(gen)


# DeploymentConfig - configuration from multiple sources


class TestDeploymentConfig:
    """DeploymentConfig loading from all configuration sources."""

    def test_defaults(self):
        cfg = DeploymentConfig()
        assert cfg.deployment_type == "single"
        assert cfg.max_rules == 50_000
        assert cfg.instance_count == 1

    def test_explicit_config(self):
        cfg = DeploymentConfig(
            deployment_type="multi_instance",
            max_rules=100_000,
            instance_count=3,
        )
        assert cfg.deployment_type == "multi_instance"
        assert cfg.max_rules == 100_000
        assert cfg.detected_from == "explicit"

    def test_from_environment(self):
        env = {
            "FLUXRULES_DEPLOYMENT_TYPE": "multi_region",
            "FLUXRULES_MAX_RULES": "200000",
            "FLUXRULES_INSTANCE_COUNT": "5",
            "FLUXRULES_REGION_COUNT": "2",
            "FLUXRULES_SORTABLE_IDS": "true",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = DeploymentConfig.from_environment()
        assert cfg.deployment_type == "multi_region"
        assert cfg.max_rules == 200_000
        assert cfg.instance_count == 5
        assert cfg.requires_sortable_ids is True
        assert cfg.detected_from == "environment"

    def test_from_json_file(self):
        data = {
            "deployment_type": "multi_instance",
            "max_rules": 75_000,
            "instance_count": 2,
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            cfg = DeploymentConfig.from_file(f.name)
        os.unlink(f.name)
        assert cfg.deployment_type == "multi_instance"
        assert cfg.max_rules == 75_000
        assert cfg.detected_from == "file"

    def test_from_yaml_file(self):
        pytest.importorskip("yaml")
        content = "deployment_type: multi_region\nmax_rules: 300000\n"
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(content)
            f.flush()
            cfg = DeploymentConfig.from_file(f.name)
        os.unlink(f.name)
        assert cfg.deployment_type == "multi_region"
        assert cfg.max_rules == 300_000

    def test_load_with_fallback_defaults(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("FLUXRULES_")}
        env.pop("HOSTNAME", None)
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = DeploymentConfig.load_with_fallback()
        assert cfg.detected_from == "auto"

    def test_load_with_fallback_env(self):
        env = {"FLUXRULES_DEPLOYMENT_TYPE": "multi_instance"}
        with mock.patch.dict(os.environ, env, clear=False):
            cfg = DeploymentConfig.load_with_fallback()
        assert cfg.detected_from == "environment"

    def test_load_with_fallback_file(self):
        data = {"deployment_type": "multi_region", "max_rules": 999}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            f.flush()
            env = {"FLUXRULES_CONFIG_FILE": f.name}
            with mock.patch.dict(os.environ, env, clear=False):
                cfg = DeploymentConfig.load_with_fallback()
        os.unlink(f.name)
        assert cfg.detected_from == "file"
        assert cfg.max_rules == 999

    def test_summary(self):
        cfg = DeploymentConfig()
        s = cfg.summary()
        assert "single" in s
        assert "50,000" in s


# Auto-detection strategy selection


class TestAutoDetection:
    """Validate that auto-detection picks the right strategy."""

    def test_single_small(self):
        cfg = DeploymentConfig(deployment_type="single", max_rules=5_000)
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.SEQUENTIAL

    def test_single_deterministic(self):
        cfg = DeploymentConfig(deployment_type="single", requires_deterministic=True)
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.HASH_BASED

    def test_multi_instance_small(self):
        cfg = DeploymentConfig(deployment_type="multi_instance", max_rules=50_000, instance_count=3)
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.HYBRID

    def test_multi_instance_large(self):
        cfg = DeploymentConfig(deployment_type="multi_instance", max_rules=200_000)
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.SNOWFLAKE

    def test_multi_region(self):
        cfg = DeploymentConfig(deployment_type="multi_region", max_rules=100_000)
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.SNOWFLAKE

    def test_multi_region_small_no_sortable(self):
        cfg = DeploymentConfig(
            deployment_type="multi_region",
            max_rules=5_000,
            requires_sortable_ids=False,
        )
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.UUID

    def test_serverless(self):
        cfg = DeploymentConfig(deployment_type="serverless")
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.UUID

    def test_no_coordination_distributed(self):
        cfg = DeploymentConfig(
            deployment_type="multi_instance",
            require_no_coordination=True,
            max_rules=50_000,
        )
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.HASH_BASED

    def test_no_coordination_large(self):
        cfg = DeploymentConfig(
            deployment_type="multi_region",
            require_no_coordination=True,
            max_rules=200_000,
        )
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.UUID

    def test_single_huge_scale(self):
        cfg = DeploymentConfig(deployment_type="single", max_rules=2_000_000)
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.SNOWFLAKE

    def test_auto_detect_classmethod(self):
        """auto_detect() with clean env should return Sequential."""
        env = {k: v for k, v in os.environ.items() if not k.startswith("FLUXRULES_")}
        env.pop("HOSTNAME", None)
        with mock.patch.dict(os.environ, env, clear=True):
            gen = RuleIDGenerator.auto_detect()
        assert gen.strategy is IDStrategy.SEQUENTIAL


# Thread safety


class TestThreadSafety:
    """Generators produce unique IDs across threads."""

    def test_sequential_threadsafe(self):
        import threading

        gen = RuleIDGenerator()
        results: list[int] = []
        lock = threading.Lock()

        def worker():
            ids = [gen.next_id() for _ in range(100)]
            with lock:
                results.extend(ids)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 1000
        assert len(set(results)) == 1000  # all unique

    def test_snowflake_threadsafe(self):
        import threading

        gen = RuleIDGenerator(strategy="snowflake", machine_id=0)
        results: list[int] = []
        lock = threading.Lock()

        def worker():
            ids = [gen.next_id() for _ in range(100)]
            with lock:
                results.extend(ids)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(set(results)) == 1000


# DeploymentType enum


class TestDeploymentType:
    """DeploymentType enum works correctly."""

    def test_enum_values(self):
        assert DeploymentType.SINGLE.value == "single"
        assert DeploymentType.MULTI_INSTANCE.value == "multi_instance"
        assert DeploymentType.MULTI_REGION.value == "multi_region"
        assert DeploymentType.SERVERLESS.value == "serverless"

    def test_config_accepts_enum(self):
        cfg = DeploymentConfig(deployment_type=DeploymentType.MULTI_INSTANCE)
        assert cfg.deployment_type == "multi_instance"

    def test_config_accepts_string(self):
        cfg = DeploymentConfig(deployment_type="multi_region")
        assert cfg.deployment_type == "multi_region"

    def test_auto_detect_with_enum(self):
        cfg = DeploymentConfig(
            deployment_type=DeploymentType.MULTI_REGION,
            max_rules=100_000,
        )
        gen = RuleIDGenerator.from_config(cfg)
        assert gen.strategy is IDStrategy.SNOWFLAKE


# DeploymentConfig.validate()


class TestDeploymentConfigValidation:
    """Config validation catches mistakes."""

    def test_valid_config_no_warnings(self):
        cfg = DeploymentConfig()
        warnings = cfg.validate()
        assert warnings == []

    def test_invalid_deployment_type(self):
        cfg = DeploymentConfig(deployment_type="invalid_type")
        with pytest.raises(ConfigValidationError, match="Invalid deployment_type"):
            cfg.validate()

    def test_max_rules_zero(self):
        cfg = DeploymentConfig(max_rules=0)
        with pytest.raises(ConfigValidationError, match="max_rules must be >= 1"):
            cfg.validate()

    def test_multi_region_low_region_count(self):
        cfg = DeploymentConfig(deployment_type="multi_region", region_count=1)
        warnings = cfg.validate()
        assert any("region_count" in w for w in warnings)

    def test_multi_instance_low_instance_count(self):
        cfg = DeploymentConfig(deployment_type="multi_instance", instance_count=1)
        warnings = cfg.validate()
        assert any("instance_count" in w for w in warnings)

    def test_invalid_expected_growth(self):
        cfg = DeploymentConfig(expected_growth="unknown")
        warnings = cfg.validate()
        assert any("expected_growth" in w for w in warnings)

    def test_valid_multi_region(self):
        cfg = DeploymentConfig(
            deployment_type="multi_region",
            region_count=3,
            instance_count=1,
        )
        warnings = cfg.validate()
        assert warnings == []


# DeploymentConfig.from_dict()


class TestDeploymentConfigFromDict:
    """from_dict() loads config from plain dicts."""

    def test_basic(self):
        cfg = DeploymentConfig.from_dict(
            {
                "deployment_type": "multi_instance",
                "max_rules": 80_000,
                "instance_count": 4,
            }
        )
        assert cfg.deployment_type == "multi_instance"
        assert cfg.max_rules == 80_000
        assert cfg.instance_count == 4
        assert cfg.detected_from == "dict"

    def test_nested_requirements(self):
        cfg = DeploymentConfig.from_dict(
            {
                "deployment_type": "single",
                "requirements": {
                    "sortable_ids": True,
                    "deterministic": True,
                },
            }
        )
        assert cfg.requires_sortable_ids is True
        assert cfg.requires_deterministic is True

    def test_nested_coordination(self):
        cfg = DeploymentConfig.from_dict(
            {
                "coordination": {
                    "redis_host": "redis.example.com",
                    "redis_port": 6380,
                },
            }
        )
        assert cfg.redis_host == "redis.example.com"
        assert cfg.redis_port == 6380

    def test_empty_dict(self):
        cfg = DeploymentConfig.from_dict({})
        assert cfg.deployment_type == "single"
        assert cfg.max_rules == 50_000

    def test_does_not_mutate_input(self):
        d = {"deployment_type": "single", "requirements": {"sortable_ids": True}}
        DeploymentConfig.from_dict(d)
        assert "requirements" in d  # original not mutated


# Default file location search in load_with_fallback


class TestDefaultFileSearch:
    """load_with_fallback searches default file locations."""

    def test_finds_fluxrules_yaml_in_cwd(self, tmp_path, monkeypatch):
        config_file = tmp_path / "fluxrules.yaml"
        config_file.write_text("deployment_type: multi_region\nmax_rules: 77777\n")
        monkeypatch.chdir(tmp_path)
        # Clear env
        env = {k: v for k, v in os.environ.items() if not k.startswith("FLUXRULES_")}
        env.pop("HOSTNAME", None)
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = DeploymentConfig.load_with_fallback()
        assert cfg.detected_from == "file"
        assert cfg.max_rules == 77_777

    def test_finds_fluxrules_json_in_cwd(self, tmp_path, monkeypatch):
        config_file = tmp_path / "fluxrules.json"
        config_file.write_text(json.dumps({"deployment_type": "serverless", "max_rules": 1234}))
        monkeypatch.chdir(tmp_path)
        env = {k: v for k, v in os.environ.items() if not k.startswith("FLUXRULES_")}
        env.pop("HOSTNAME", None)
        with mock.patch.dict(os.environ, env, clear=True):
            cfg = DeploymentConfig.load_with_fallback()
        assert cfg.deployment_type == "serverless"
        assert cfg.max_rules == 1234
