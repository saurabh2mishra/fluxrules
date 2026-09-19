"""Tests for RuntimeConfigManager."""

from fluxrules.config import RuntimeConfig, RuntimeConfigManager


class TestRuntimeConfigManager:
    """Test configuration manager."""

    def setup_method(self):
        """Reset manager before each test."""
        RuntimeConfigManager.reset()

    def teardown_method(self):
        """Reset manager after each test."""
        RuntimeConfigManager.reset()

    def test_initialize_sets_instance(self):
        """Initialize() should set the instance."""
        config = RuntimeConfig.default()
        RuntimeConfigManager.initialize(config)

        assert RuntimeConfigManager.get() is config
        assert RuntimeConfigManager.is_initialized()

    def test_get_before_initialize_returns_default(self):
        """get() before initialize() should return default."""
        config = RuntimeConfigManager.get()
        assert config is not None
        assert isinstance(config, RuntimeConfig)

    def test_initialize_twice_is_ignored(self, caplog):
        """Calling initialize() twice should be ignored."""
        import logging

        # Ensure clean state
        RuntimeConfigManager.reset()

        config1 = RuntimeConfig.default()
        config2 = RuntimeConfig.default()

        # Set log level to capture warnings
        logging.getLogger("fluxrules.config.manager").setLevel(logging.WARNING)
        caplog.set_level(logging.WARNING)

        RuntimeConfigManager.initialize(config1)
        # Second init should be ignored
        RuntimeConfigManager.initialize(config2)

        # Verify that the first config is still used (second init was ignored)
        assert RuntimeConfigManager.get() is config1
        # Verify that config2 was NOT used
        assert RuntimeConfigManager.get() is not config2

    def test_reset_clears_state(self):
        """reset() should clear initialization state."""
        config = RuntimeConfig.default()
        RuntimeConfigManager.initialize(config)
        RuntimeConfigManager.reset()

        assert not RuntimeConfigManager.is_initialized()
        new_config = RuntimeConfigManager.get()
        assert new_config is not config

    def test_set_for_testing(self):
        """set() should allow overriding config for testing."""
        config = RuntimeConfig.default()
        RuntimeConfigManager.set(config)

        assert RuntimeConfigManager.get() is config
        assert RuntimeConfigManager.is_initialized()

    def test_default_config_has_memory_backends(self):
        """Default config should use in-memory backends."""
        config = RuntimeConfigManager.get()
        assert config.queue.backend == "memory"
        assert config.cache.backend == "memory"
        assert config.repository.backend == "memory"
