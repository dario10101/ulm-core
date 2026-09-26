"""Pruebas unitarias de los endpoints de gastos y sus catalogos.

El engine, el cliente y el aislamiento por test viven en conftest.py. A
diferencia de weights/meals, aca los catalogos no vienen sembrados por
`ensure_default_user` (eso es solo el usuario), asi que cada test crea las
filas de categoria/metodo de pago/tag que necesita.
"""

from datetime import date

from app.db.models import finance as finance_model  # noqa: F401
from app.db.models.finance import Category, Expense, PaymentMethod, Tag
from app.db.models.user import User
from tests.conftest import client


def _seed_catalog(db_session, *, user_id: int = 1) -> tuple[int, int, int]:
    """Crea una categoria, un metodo de pago y un tag ENABLED; devuelve sus ids."""
    category = Category(name="Groceries", icon_key="shopping-cart", color_key="lime")
    payment_method = PaymentMethod(name="Cash", icon_key="banknote", color_key="green")
    tag = Tag(user_id=user_id, name="NEEDED", color_key="emerald")
    db_session.add_all([category, payment_method, tag])
    db_session.commit()
    return category.id, payment_method.id, tag.id


def test_get_expense_options_only_returns_enabled(db_session):
    category_id, payment_method_id, tag_id = _seed_catalog(db_session)
    disabled_category = Category(
        name="Old", icon_key="package", color_key="slate", status="DISABLED"
    )
    db_session.add(disabled_category)
    db_session.commit()

    response = client.get("/api/v1/expenses/options")

    assert response.status_code == 200
    body = response.json()
    category_ids = [c["id"] for c in body["categories"]]
    assert category_id in category_ids
    assert disabled_category.id not in category_ids
    assert [p["id"] for p in body["payment_methods"]] == [payment_method_id]
    assert [t["id"] for t in body["tags"]] == [tag_id]


def test_create_expense(db_session):
    category_id, payment_method_id, tag_id = _seed_catalog(db_session)

    response = client.post(
        "/api/v1/expenses/",
        json={
            "name": "Mercado",
            "amount": 25000,
            "recorded_on": "2026-09-26",
            "note": "Mercado de la semana",
            "payment_method_id": payment_method_id,
            "category_id": category_id,
            "tag_ids": [tag_id],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Mercado"
    assert body["amount"] == 25000
    assert body["recorded_on"] == "2026-09-26"
    assert body["note"] == "Mercado de la semana"
    assert body["category"]["id"] == category_id
    assert body["payment_method"]["id"] == payment_method_id
    assert [t["id"] for t in body["tags"]] == [tag_id]
    assert body["user_id"] == 1


def test_create_expense_missing_required_field_returns_422():
    response = client.post("/api/v1/expenses/", json={"recorded_on": "2026-09-26"})
    assert response.status_code == 422


def test_create_expense_requires_name(db_session):
    category_id, payment_method_id, _tag_id = _seed_catalog(db_session)

    response = client.post(
        "/api/v1/expenses/",
        json={
            "amount": 1000,
            "recorded_on": "2026-09-26",
            "payment_method_id": payment_method_id,
            "category_id": category_id,
        },
    )
    assert response.status_code == 422


def test_create_expense_requires_positive_amount(db_session):
    category_id, payment_method_id, _tag_id = _seed_catalog(db_session)

    response = client.post(
        "/api/v1/expenses/",
        json={
            "name": "Test",
            "amount": 0,
            "recorded_on": "2026-09-26",
            "payment_method_id": payment_method_id,
            "category_id": category_id,
        },
    )
    assert response.status_code == 422


def test_create_expense_with_unknown_category_returns_404(db_session):
    _category_id, payment_method_id, _tag_id = _seed_catalog(db_session)

    response = client.post(
        "/api/v1/expenses/",
        json={
            "name": "Test",
            "amount": 1000,
            "recorded_on": "2026-09-26",
            "payment_method_id": payment_method_id,
            "category_id": 9999,
        },
    )
    assert response.status_code == 404


def test_create_expense_with_unknown_tag_returns_404(db_session):
    category_id, payment_method_id, _tag_id = _seed_catalog(db_session)

    response = client.post(
        "/api/v1/expenses/",
        json={
            "name": "Test",
            "amount": 1000,
            "recorded_on": "2026-09-26",
            "payment_method_id": payment_method_id,
            "category_id": category_id,
            "tag_ids": [9999],
        },
    )
    assert response.status_code == 404


def test_list_expenses_is_paginated_and_filters_by_date_range(db_session):
    category_id, payment_method_id, _tag_id = _seed_catalog(db_session)

    for day in ["2026-08-02", "2026-08-05", "2026-08-10"]:
        client.post(
            "/api/v1/expenses/",
            json={
                "name": "Test",
                "amount": 1000,
                "recorded_on": day,
                "payment_method_id": payment_method_id,
                "category_id": category_id,
            },
        )

    page_response = client.get("/api/v1/expenses/", params={"page": 1, "page_size": 2})
    assert page_response.status_code == 200
    page_body = page_response.json()
    assert page_body["page"] == 1
    assert page_body["page_size"] == 2
    assert len(page_body["items"]) == 2
    assert page_body["total"] == 3

    filtered_response = client.get(
        "/api/v1/expenses/",
        params={"start_date": "2026-08-03", "end_date": "2026-08-10"},
    )
    filtered_body = filtered_response.json()
    assert all(
        "2026-08-03" <= item["recorded_on"] <= "2026-08-10" for item in filtered_body["items"]
    )


def test_another_users_expense_is_not_listed(db_session):
    category_id, payment_method_id, _tag_id = _seed_catalog(db_session)
    other = User(id=999, name="Otra persona", email="otra@example.com", timezone="America/Bogota")
    db_session.add(other)
    db_session.flush()

    other_expense = Expense(
        user_id=other.id,
        name="Ajeno",
        amount=5000,
        recorded_on=date(2026, 8, 1),
        payment_method_id=payment_method_id,
        category_id=category_id,
    )
    db_session.add(other_expense)
    db_session.commit()

    body = client.get("/api/v1/expenses/").json()

    assert body["total"] == 0
