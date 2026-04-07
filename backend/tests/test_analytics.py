from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api import deps
from app.database import Base, get_db
from app.main import app
from app.models.rule import Rule
from app.services import analytics_service as analytics_module
from app.services.analytics_service import AnalyticsService
from app.analytics.store import InMemoryAnalyticsStore


SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class FakeUser:
    id = 1
    username = "tester"
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
    analytics_module._analytics_service = AnalyticsService(store=InMemoryAnalyticsStore())


def _client():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[deps.get_current_user] = lambda: FakeUser()
    return TestClient(app)


def _seed_rules(db):
    db.add(
        Rule(
            name="rule_hot",
            description="hot",
            group="g1",
            priority=1,
            enabled=True,
            condition_dsl={"type": "condition", "field": "amount", "op": ">", "value": 10},
            action="approve",
            created_by=1,
        )
    )
    db.add(
        Rule(
            name="rule_cold",
            description="cold",
            group="g1",
            priority=2,
            enabled=True,
            condition_dsl={"type": "condition", "field": "country", "op": "==", "value": "US"},
            action="review",
            created_by=1,
        )
    )
    db.commit()


def test_analytics_summary_and_top_rules():
    db = TestingSessionLocal()
    _seed_rules(db)
    service = analytics_module.get_analytics_service()

    service.record_event_processed(20.0)
    service.record_rule_execution("1", 12.0, {"amount": 99}, "[✓ amount > 10]")

    summary = service.get_runtime_summary(db)
    assert summary.total_rules == 2
    assert summary.triggered_rules == 1
    assert summary.coverage_pct == 50.0

    top = service.get_top_rules(db, limit=10)
    assert top.top_hot_rules[0].rule_id == "1"
    assert any(x.rule_id == "2" for x in top.cold_rules)
    db.close()


def test_analytics_api_runtime_and_coverage():
    client = _client()
    db = TestingSessionLocal()
    _seed_rules(db)
    db.close()

    service = analytics_module.get_analytics_service()
    service.record_event_processed(10.0)
    service.record_rule_execution("1", 5.0, {"amount": 50}, "[✓ amount > 10] | Matching conditions: amount")

    runtime = client.get("/api/v1/analytics/runtime")
    assert runtime.status_code == 200
    assert runtime.json()["summary"]["events_processed"] >= 1

    coverage = client.get("/api/v1/analytics/coverage")
    assert coverage.status_code == 200
    payload = coverage.json()
    assert payload["summary"]["coverage_pct"] == 50.0
    assert "2" in payload["never_fired_rule_ids"]

    explanations = client.get("/api/v1/analytics/explanations?limit=5")
    assert explanations.status_code == 200
    assert len(explanations.json()["items"]) >= 1
