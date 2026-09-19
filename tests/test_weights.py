"""Pruebas unitarias de los endpoints de registros de peso.

Usa SQLite en memoria (igual que test_dummy.py) para no depender de Postgres.
"""

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base_class import Base
from app.db.seed import ensure_default_user
from app.db.session import get_db
from app.main import app

# Importar los modelos para que sus tablas queden registradas en Base.metadata
from app.db.models import weight as weight_model  # noqa: F401
from app.db.models import user as user_model  # noqa: F401

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)
Base.metadata.create_all(bind=test_engine)

seed_db = TestSessionLocal()
ensure_default_user(seed_db)
seed_db.close()


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)


def test_create_weight():
    response = client.post(
        "/api/v1/weights/",
        json={"weight_kg": 72.4, "recorded_on": "2026-08-01", "note": "post workout"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["weight_kg"] == 72.4
    assert body["recorded_on"] == "2026-08-01"
    assert body["note"] == "post workout"
    assert body["user_id"] == 1


def test_create_weight_missing_required_field_returns_422():
    response = client.post("/api/v1/weights/", json={"note": "sin peso ni fecha"})
    assert response.status_code == 422


def test_create_weight_requires_positive_value():
    response = client.post(
        "/api/v1/weights/", json={"weight_kg": 0, "recorded_on": "2026-08-01"}
    )
    assert response.status_code == 422


def test_list_weights_is_paginated_and_filters_by_date_range():
    for day, value in [("2026-08-02", 73.0), ("2026-08-05", 73.5), ("2026-08-10", 74.0)]:
        client.post("/api/v1/weights/", json={"weight_kg": value, "recorded_on": day})

    page_response = client.get("/api/v1/weights/", params={"page": 1, "page_size": 2})
    assert page_response.status_code == 200
    page_body = page_response.json()
    assert page_body["page"] == 1
    assert page_body["page_size"] == 2
    assert len(page_body["items"]) == 2
    assert page_body["total"] >= 4

    filtered_response = client.get(
        "/api/v1/weights/",
        params={"start_date": "2026-08-03", "end_date": "2026-08-10"},
    )
    filtered_body = filtered_response.json()
    assert all(
        "2026-08-03" <= item["recorded_on"] <= "2026-08-10" for item in filtered_body["items"]
    )


def test_update_and_delete_weight():
    create_response = client.post(
        "/api/v1/weights/", json={"weight_kg": 80.0, "recorded_on": "2026-09-01"}
    )
    weight_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/v1/weights/{weight_id}",
        json={"weight_kg": 79.5, "recorded_on": "2026-09-02", "note": "ajustado"},
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["weight_kg"] == 79.5
    assert updated["note"] == "ajustado"

    delete_response = client.delete(f"/api/v1/weights/{weight_id}")
    assert delete_response.status_code == 204

    update_missing_response = client.put(
        f"/api/v1/weights/{weight_id}",
        json={"weight_kg": 70.0, "recorded_on": "2026-09-03"},
    )
    assert update_missing_response.status_code == 404

    delete_missing_response = client.delete(f"/api/v1/weights/{weight_id}")
    assert delete_missing_response.status_code == 404
