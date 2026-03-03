import pytest
from app.main import app

def _fake_get_current_user():
    class User:
        id = 1
        username = "testuser"
        email = "testuser@example.com"
        role = "business"
        is_active = True
    return User()

@pytest.fixture(scope="session", autouse=True)
def override_auth_dependency():
    try:
        from app.api import deps
        app.dependency_overrides[deps.get_current_user] = _fake_get_current_user
        yield
        app.dependency_overrides.pop(deps.get_current_user, None)
    except ImportError:
        yield
