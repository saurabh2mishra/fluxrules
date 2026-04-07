from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.database import Base, get_db
from app.main import app
from app.models.rule import Rule


SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class FakeUser:
    id = 1
    username = "fallback-user"
    role = "business"


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def test_submit_event_sync_fallback_without_redis(monkeypatch):
    db = TestingSessionLocal()
    db.add(
        Rule(
            name="fallback_rule",
            description="sync fallback",
            group="g1",
            priority=1,
            enabled=True,
            condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 10},
            action="notify",
            created_by=1,
        )
    )
    db.commit()
    db.close()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = lambda: FakeUser()

    # simulate Redis unavailable
    monkeypatch.setattr("app.api.routes.events.get_redis_client", lambda: None)

    client = TestClient(app)
    response = client.post(
        "/api/v1/event",
        json={"event_type": "payment", "data": {"amount": 100}, "metadata": {}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "processed"
    assert "Redis is unavailable" in payload["message"]
