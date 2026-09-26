"""Pruebas unitarias de los endpoints de registros de comida.

El engine, el cliente y el aislamiento por test viven en conftest.py. El
usuario semilla (id 1) tiene timezone "America/Bogota" (ver
app.db.seed.ensure_default_user), asi que "2026-08-01T13:30:00" se guarda
como "2026-08-01T18:30:00+00:00" (UTC-5, sin horario de verano).
"""

from datetime import UTC, datetime

from app.db.models import meal as meal_model  # noqa: F401
from app.db.models.meal import Meal
from app.db.models.user import User
from tests.conftest import client


def test_create_meal_with_components():
    response = client.post(
        "/api/v1/meals/",
        json={
            "recorded_on": "2026-08-01T13:30:00",
            "meal_type": "LUNCH",
            "meal_size": 80,
            "components": [
                {"name": "Arroz", "percent": 40},
                {"name": "  huevo  ", "percent": 60},
            ],
            "drink": "agua",
            "note": "con la familia",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["meal_type"] == "LUNCH"
    assert body["meal_size"] == 80
    assert body["meal_content"] == "ARROZ:40;HUEVO:60"
    assert body["drink"] == "AGUA"
    assert body["note"] == "con la familia"
    assert body["recorded_on"] == "2026-08-01T13:30:00"
    assert body["user_id"] == 1


def test_meal_content_is_normalized_and_alphabetically_sorted():
    response = client.post(
        "/api/v1/meals/",
        json={
            "recorded_on": "2026-08-01T13:30:00",
            "meal_type": "DINNER",
            "meal_size": 50,
            "components": [
                {"name": "Pan integral!!", "percent": 30},
                {"name": "Jamón   serrano", "percent": 35},
                {"name": "cafe con leche", "percent": 35},
            ],
        },
    )
    assert response.status_code == 201
    # Alfabetico por nombre ya normalizado: CAFE CON LECHE, JAMON SERRANO, PAN INTEGRAL
    assert response.json()["meal_content"] == "CAFE CON LECHE:35;JAMON SERRANO:35;PAN INTEGRAL:30"


def test_create_meal_only_drink_is_valid():
    response = client.post(
        "/api/v1/meals/",
        json={
            "recorded_on": "2026-08-01T07:00:00",
            "meal_type": "BREAKFAST",
            "meal_size": 20,
            "components": [],
            "drink": "cafe",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["meal_content"] is None
    assert body["drink"] == "CAFE"


def test_create_meal_requires_components_or_drink():
    response = client.post(
        "/api/v1/meals/",
        json={
            "recorded_on": "2026-08-01T07:00:00",
            "meal_type": "BREAKFAST",
            "meal_size": 20,
            "components": [],
        },
    )
    assert response.status_code == 422


def test_create_meal_rejects_timezone_aware_datetime():
    response = client.post(
        "/api/v1/meals/",
        json={
            "recorded_on": "2026-08-01T07:00:00Z",
            "meal_type": "BREAKFAST",
            "meal_size": 20,
            "components": [{"name": "HUEVO", "percent": 100}],
        },
    )
    assert response.status_code == 422


def test_create_meal_missing_required_field_returns_422():
    response = client.post("/api/v1/meals/", json={"meal_size": 50})
    assert response.status_code == 422


def test_list_meals_is_paginated_and_filters_by_date_range():
    for day in ["2026-08-02", "2026-08-05", "2026-08-10"]:
        client.post(
            "/api/v1/meals/",
            json={
                "recorded_on": f"{day}T12:00:00",
                "meal_type": "LUNCH",
                "meal_size": 50,
                "components": [{"name": "ARROZ", "percent": 100}],
            },
        )

    page_response = client.get("/api/v1/meals/", params={"page": 1, "page_size": 2})
    assert page_response.status_code == 200
    page_body = page_response.json()
    assert page_body["page"] == 1
    assert page_body["page_size"] == 2
    assert len(page_body["items"]) == 2
    assert page_body["total"] == 3

    filtered_response = client.get(
        "/api/v1/meals/",
        params={"start_date": "2026-08-03", "end_date": "2026-08-10"},
    )
    filtered_body = filtered_response.json()
    assert all(
        "2026-08-03" <= item["recorded_on"][:10] <= "2026-08-10" for item in filtered_body["items"]
    )


def test_update_and_delete_meal():
    create_response = client.post(
        "/api/v1/meals/",
        json={
            "recorded_on": "2026-09-01T20:00:00",
            "meal_type": "DINNER",
            "meal_size": 60,
            "components": [{"name": "SOPA", "percent": 100}],
        },
    )
    meal_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/v1/meals/{meal_id}",
        json={
            "recorded_on": "2026-09-01T20:30:00",
            "meal_type": "LATE_NIGHT_SNACK",
            "meal_size": 30,
            "components": [{"name": "GALLETAS", "percent": 100}],
            "note": "ajustado",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["meal_type"] == "LATE_NIGHT_SNACK"
    assert updated["meal_content"] == "GALLETAS:100"
    assert updated["note"] == "ajustado"

    delete_response = client.delete(f"/api/v1/meals/{meal_id}")
    assert delete_response.status_code == 204

    update_missing_response = client.put(
        f"/api/v1/meals/{meal_id}",
        json={
            "recorded_on": "2026-09-01T20:30:00",
            "meal_type": "DINNER",
            "meal_size": 30,
            "components": [{"name": "SOPA", "percent": 100}],
        },
    )
    assert update_missing_response.status_code == 404

    delete_missing_response = client.delete(f"/api/v1/meals/{meal_id}")
    assert delete_missing_response.status_code == 404


# --- Aislamiento por usuario: un registro ajeno no se puede tocar ni ver ---


def _other_users_meal(db_session) -> int:
    """Crea un usuario distinto al quemado y un registro de comida suyo."""
    other = User(id=999, name="Otra persona", email="otra@example.com", timezone="America/Bogota")
    db_session.add(other)
    db_session.flush()
    record = Meal(
        user_id=other.id,
        recorded_on=datetime(2026, 8, 1, 12, 0, tzinfo=UTC),
        meal_type="LUNCH",
        meal_size=50,
        meal_content="ARROZ:100",
    )
    db_session.add(record)
    db_session.commit()
    return record.id


def test_update_of_another_users_meal_returns_404(db_session):
    meal_id = _other_users_meal(db_session)

    response = client.put(
        f"/api/v1/meals/{meal_id}",
        json={
            "recorded_on": "2026-08-01T12:00:00",
            "meal_type": "LUNCH",
            "meal_size": 10,
            "components": [{"name": "ajeno", "percent": 100}],
        },
    )

    assert response.status_code == 404
    assert db_session.get(Meal, meal_id).meal_content == "ARROZ:100"


def test_delete_of_another_users_meal_returns_404(db_session):
    meal_id = _other_users_meal(db_session)

    response = client.delete(f"/api/v1/meals/{meal_id}")

    assert response.status_code == 404
    assert db_session.get(Meal, meal_id) is not None


def test_another_users_meal_is_not_listed(db_session):
    _other_users_meal(db_session)

    body = client.get("/api/v1/meals/").json()

    assert body["total"] == 0
