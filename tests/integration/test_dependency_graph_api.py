from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from fluxrules.api import deps
from fluxrules.api.app import create_app
from fluxrules.api.database import Base, get_db
from fluxrules.api.models.rule import Rule

app = create_app()

SQLALCHEMY_DATABASE_URL = "sqlite://"
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def _fake_user():
    class U:
        id = 1
        username = "testuser"
        email = "t@t.com"
        role = "business"
        is_active = True

    return U()


app.dependency_overrides[deps.get_current_user] = _fake_user
app.dependency_overrides[deps.get_current_admin] = _fake_user


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db


def setup_function():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)


def seed_rules():
    db = TestingSessionLocal()
    db.add_all(
        [
            Rule(
                name="r1",
                group="g1",
                priority=1,
                enabled=True,
                condition_dsl={
                    "type": "condition",
                    "field": "amount",
                    "op": ">",
                    "value": 10,
                },
                action="a",
                created_by=1,
            ),
            Rule(
                name="r2",
                group="g1",
                priority=2,
                enabled=True,
                condition_dsl={
                    "type": "condition",
                    "field": "amount",
                    "op": "<",
                    "value": 200,
                },
                action="a",
                created_by=1,
            ),
            Rule(
                name="r3",
                group="g2",
                priority=3,
                enabled=True,
                condition_dsl={
                    "type": "condition",
                    "field": "country",
                    "op": "==",
                    "value": "US",
                },
                action="a",
                created_by=1,
            ),
        ]
    )
    db.commit()
    db.close()


def test_dependency_summary_and_filtered_graph():
    app.dependency_overrides[get_db] = override_get_db
    seed_rules()
    client = TestClient(app)

    summary = client.get("/api/v1/rules/graph/summary")
    assert summary.status_code == 200
    payload = summary.json()
    assert payload["total_rules"] == 3
    assert payload["pair_count"] >= 1
    assert any(row["field"] == "amount" for row in payload["top_shared_fields"])

    graph = client.get("/api/v1/rules/graph/dependencies?field=amount&max_nodes=100")
    assert graph.status_code == 200
    gp = graph.json()
    assert gp["summary_only"] is False
    assert len(gp["nodes"]) == 2
    assert len(gp["edges"]) >= 1
