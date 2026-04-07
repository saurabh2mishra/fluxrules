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

def _fake_get_current_admin():
    class User:
        id = 1
        username = "admin"
        email = "admin@example.com"
        role = "admin"
        is_active = True
    return User()

@pytest.fixture(scope="session", autouse=True)
def override_auth_dependency():
    try:
        from app.api import deps
        app.dependency_overrides[deps.get_current_user] = _fake_get_current_user
        app.dependency_overrides[deps.get_current_admin] = _fake_get_current_admin
        yield
        app.dependency_overrides.pop(deps.get_current_user, None)
        app.dependency_overrides.pop(deps.get_current_admin, None)
    except ImportError:
        yield
