"""Tests for the new action registry system."""

import asyncio

import pytest

from fluxrules.plugins.actions import action, action_registry


@pytest.fixture
def clean_registry():
    """Fixture to reset registry before and after each test."""
    action_registry.reset()
    yield
    action_registry.reset()


class TestActionRegistration:
    """Test action registration via decorator."""

    def test_register_simple_action(self, clean_registry):
        """Test registering a simple sync action."""

        @action_registry.register(
            name="test_action",
            description="Test action",
            category="test",
        )
        def test_func(param1: str, param2: int) -> dict:
            return {"result": "success"}

        assert action_registry.has("test_action")
        metadata = action_registry.get("test_action")
        assert metadata.name == "test_action"
        assert metadata.description == "Test action"
        assert metadata.category == "test"
        assert not metadata.is_async
        assert len(metadata.parameters) == 2

    def test_register_async_action(self, clean_registry):
        """Test registering an async action."""

        @action_registry.register(
            name="async_action",
            description="Async action",
            category="async",
            async_handler=True,
        )
        async def async_func(param: str) -> dict:
            return {"result": "async_success"}

        metadata = action_registry.get("async_action")
        assert metadata.is_async

    def test_action_decorator_shorthand(self, clean_registry):
        """Test the @action shorthand decorator."""

        @action(
            name="shorthand_action",
            description="Shorthand test",
            category="test",
        )
        def test_func():
            return {}

        assert action_registry.has("shorthand_action")


class TestParameterExtraction:
    """Test automatic parameter extraction and metadata."""

    def test_extract_parameters_with_types(self, clean_registry):
        """Test extracting typed parameters."""

        @action_registry.register(
            name="typed_params",
            description="Test",
            category="test",
        )
        def func(name: str, age: int, active: bool = True) -> dict:
            return {}

        metadata = action_registry.get("typed_params")
        assert len(metadata.parameters) == 3

        # Check each parameter
        assert metadata.parameters[0].name == "name"
        assert metadata.parameters[0].type_hint is str
        assert metadata.parameters[0].required

        assert metadata.parameters[1].name == "age"
        assert metadata.parameters[1].type_hint is int
        assert metadata.parameters[1].required

        assert metadata.parameters[2].name == "active"
        assert metadata.parameters[2].type_hint is bool
        assert not metadata.parameters[2].required
        assert metadata.parameters[2].default is True

    def test_extract_untyped_parameters(self, clean_registry):
        """Test extracting parameters without type hints."""

        @action_registry.register(
            name="untyped_params",
            description="Test",
            category="test",
        )
        def func(param1, param2=None):
            return {}

        metadata = action_registry.get("untyped_params")
        assert len(metadata.parameters) == 2
        assert metadata.parameters[0].type_hint is not None  # Should be Any


class TestDiscovery:
    """Test action discovery and listing."""

    def test_list_actions(self, clean_registry):
        """Test listing all registered actions."""

        @action(name="action1", description="First", category="cat1")
        def f1():
            return {}

        @action(name="action2", description="Second", category="cat2")
        def f2():
            return {}

        actions = action_registry.list_actions()
        assert len(actions) == 2
        assert "action1" in actions
        assert "action2" in actions

    def test_get_actions_by_category(self, clean_registry):
        """Test getting actions by category."""

        @action(name="alert1", description="Alert", category="alerts")
        def f1():
            return {}

        @action(name="alert2", description="Alert", category="alerts")
        def f2():
            return {}

        @action(name="log1", description="Log", category="logging")
        def f3():
            return {}

        alerts = action_registry.get_actions_by_category("alerts")
        assert len(alerts) == 2
        assert all(a.category == "alerts" for a in alerts)

        logs = action_registry.get_actions_by_category("logging")
        assert len(logs) == 1

    def test_list_actions_info(self, clean_registry):
        """Test getting action info for UI display."""

        @action(
            name="test_action",
            description="Test description",
            category="test",
        )
        def func(param1: str, param2: int = 5) -> dict:
            return {}

        info_list = action_registry.list_actions_info()
        assert len(info_list) == 1

        info = info_list[0]
        assert info["name"] == "test_action"
        assert info["description"] == "Test description"
        assert info["category"] == "test"
        assert not info["async"]
        assert len(info["parameters"]) == 2

    def test_get_action_signature(self, clean_registry):
        """Test getting action signature."""

        @action(name="test_action", description="Test", category="test")
        def func(param1: str, param2: int) -> dict:
            return {}

        sig = action_registry.get_action_signature("test_action")
        assert sig is not None
        assert "test_action" in sig
        assert "param1" in sig


class TestParameterValidation:
    """Test parameter validation."""

    def test_validate_valid_parameters(self, clean_registry):
        """Test validation with valid parameters."""

        @action(name="test", description="Test", category="test")
        def func(name: str, age: int, email: str | None = None):
            return {}

        is_valid, error = action_registry.validate_parameters(
            "test", name="John", age=30, email="john@example.com"
        )
        assert is_valid
        assert error == ""

    def test_validate_missing_required_parameter(self, clean_registry):
        """Test validation with missing required parameter."""

        @action(name="test", description="Test", category="test")
        def func(name: str, age: int):
            return {}

        is_valid, error = action_registry.validate_parameters(
            "test",
            name="John",  # Missing 'age'
        )
        assert not is_valid
        assert "age" in error

    def test_validate_unknown_parameter(self, clean_registry):
        """Test validation with unknown parameter."""

        @action(name="test", description="Test", category="test")
        def func(name: str):
            return {}

        is_valid, error = action_registry.validate_parameters(
            "test", name="John", unknown_param="value"
        )
        assert not is_valid
        assert "unknown_param" in error

    def test_validate_unknown_action(self, clean_registry):
        """Test validation for non-existent action."""

        is_valid, error = action_registry.validate_parameters("nonexistent", param="value")
        assert not is_valid
        assert "Unknown action" in error


class TestSyncExecution:
    """Test synchronous action execution."""

    def test_execute_simple_action(self, clean_registry):
        """Test executing a simple action."""

        @action(name="test", description="Test", category="test")
        def func(value: str) -> dict:
            return {"result": value}

        result = action_registry.execute("test", value="success")
        assert result["success"]
        assert result["action"] == "test"
        assert result["result"]["result"] == "success"

    def test_execute_with_defaults(self, clean_registry):
        """Test executing with default parameters."""

        @action(name="test", description="Test", category="test")
        def func(name: str, greeting: str = "Hello") -> dict:
            return {"message": f"{greeting} {name}"}

        result = action_registry.execute("test", name="World")
        assert result["success"]
        assert "Hello World" in result["result"]["message"]

    def test_execute_unknown_action(self, clean_registry):
        """Test executing non-existent action."""

        with pytest.raises(ValueError, match="Unknown action"):
            action_registry.execute("nonexistent", param="value")

    def test_execute_async_action_as_sync(self, clean_registry):
        """Test that executing async action as sync raises error."""

        @action(
            name="async_action",
            description="Test",
            category="test",
            async_handler=True,
        )
        async def func():
            return {}

        with pytest.raises(ValueError, match="Use execute_async"):
            action_registry.execute("async_action")

    def test_execute_action_exception(self, clean_registry):
        """Test execution error handling."""

        @action(name="failing", description="Test", category="test")
        def func():
            raise ValueError("Intentional error")

        result = action_registry.execute("failing")
        assert not result["success"]
        assert "Intentional error" in result["error"]


class TestAsyncExecution:
    """Test asynchronous action execution."""

    @pytest.mark.asyncio
    async def test_execute_async_action(self, clean_registry):
        """Test executing an async action."""

        @action(
            name="async_test",
            description="Test",
            category="test",
            async_handler=True,
        )
        async def func(value: str) -> dict:
            await asyncio.sleep(0.01)
            return {"result": value}

        result = await action_registry.execute_async("async_test", value="success")
        assert result["success"]
        assert result["action"] == "async_test"
        assert result["result"]["result"] == "success"

    @pytest.mark.asyncio
    async def test_execute_sync_action_as_async(self, clean_registry):
        """Test that executing sync action as async raises error."""

        @action(name="sync_action", description="Test", category="test")
        def func():
            return {}

        with pytest.raises(ValueError, match="Use execute\\(\\)"):
            await action_registry.execute_async("sync_action")

    @pytest.mark.asyncio
    async def test_execute_async_action_exception(self, clean_registry):
        """Test async execution error handling."""

        @action(
            name="async_failing",
            description="Test",
            category="test",
            async_handler=True,
        )
        async def func():
            raise ValueError("Async intentional error")

        result = await action_registry.execute_async("async_failing")
        assert not result["success"]
        assert "Async intentional error" in result["error"]


class TestRegistryReset:
    """Test registry reset functionality."""

    def test_reset_clears_registry(self, clean_registry):
        """Test that reset clears all actions."""

        @action(name="action1", description="Test", category="test")
        def f1():
            return {}

        @action(name="action2", description="Test", category="test")
        def f2():
            return {}

        assert len(action_registry.list_actions()) == 2

        action_registry.reset()

        assert len(action_registry.list_actions()) == 0
        assert not action_registry.has("action1")
        assert not action_registry.has("action2")


class TestDocstringExtraction:
    """Test extraction of docstrings and documentation."""

    def test_extract_docstring(self, clean_registry):
        """Test that docstrings are extracted."""

        @action(name="documented", description="Test", category="test")
        def func(param: str) -> dict:
            """This is a detailed function docstring.

            It has multiple lines and detailed information.
            """
            return {}

        metadata = action_registry.get("documented")
        assert metadata.doc is not None
        assert "detailed function docstring" in metadata.doc


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
