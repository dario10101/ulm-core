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


def test_update_and_delete_expense(db_session):
    category_id, payment_method_id, tag_id = _seed_catalog(db_session)
    other_category = Category(name="Fuel", icon_key="fuel", color_key="orange")
    db_session.add(other_category)
    db_session.commit()

    create_response = client.post(
        "/api/v1/expenses/",
        json={
            "name": "Mercado",
            "amount": 25000,
            "recorded_on": "2026-09-01",
            "payment_method_id": payment_method_id,
            "category_id": category_id,
            "tag_ids": [tag_id],
        },
    )
    expense_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/v1/expenses/{expense_id}",
        json={
            "name": "Gasolina",
            "amount": 40000,
            "recorded_on": "2026-09-02",
            "note": "ajustado",
            "payment_method_id": payment_method_id,
            "category_id": other_category.id,
            "tag_ids": [],
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "Gasolina"
    assert updated["amount"] == 40000
    assert updated["category"]["id"] == other_category.id
    assert updated["note"] == "ajustado"
    assert updated["tags"] == []

    delete_response = client.delete(f"/api/v1/expenses/{expense_id}")
    assert delete_response.status_code == 204

    update_missing_response = client.put(
        f"/api/v1/expenses/{expense_id}",
        json={
            "name": "Gasolina",
            "amount": 1000,
            "recorded_on": "2026-09-03",
            "payment_method_id": payment_method_id,
            "category_id": category_id,
        },
    )
    assert update_missing_response.status_code == 404

    delete_missing_response = client.delete(f"/api/v1/expenses/{expense_id}")
    assert delete_missing_response.status_code == 404


def test_update_of_another_users_expense_returns_404(db_session):
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

    response = client.put(
        f"/api/v1/expenses/{other_expense.id}",
        json={
            "name": "Ajeno editado",
            "amount": 1,
            "recorded_on": "2026-08-01",
            "payment_method_id": payment_method_id,
            "category_id": category_id,
        },
    )

    assert response.status_code == 404
    assert db_session.get(Expense, other_expense.id).name == "Ajeno"


def test_delete_of_another_users_expense_returns_404(db_session):
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

    response = client.delete(f"/api/v1/expenses/{other_expense.id}")

    assert response.status_code == 404
    assert db_session.get(Expense, other_expense.id) is not None


def test_list_expenses_filters_by_category_payment_method_tag_and_amount_range(db_session):
    category_id, payment_method_id, tag_id = _seed_catalog(db_session)
    other_category = Category(name="Fuel", icon_key="fuel", color_key="orange")
    other_payment_method = PaymentMethod(name="PSE", icon_key="landmark", color_key="indigo")
    other_tag = Tag(user_id=1, name="WANTED", color_key="amber")
    db_session.add_all([other_category, other_payment_method, other_tag])
    db_session.commit()

    # Coincide con todos los filtros que se van a probar.
    client.post(
        "/api/v1/expenses/",
        json={
            "name": "Mercado",
            "amount": 25000,
            "recorded_on": "2026-09-01",
            "payment_method_id": payment_method_id,
            "category_id": category_id,
            "tag_ids": [tag_id],
        },
    )
    # No coincide con ninguno (otra categoria, otro metodo, otro tag, otro monto).
    client.post(
        "/api/v1/expenses/",
        json={
            "name": "Gasolina",
            "amount": 90000,
            "recorded_on": "2026-09-02",
            "payment_method_id": other_payment_method.id,
            "category_id": other_category.id,
            "tag_ids": [other_tag.id],
        },
    )

    by_category = client.get("/api/v1/expenses/", params={"category_ids": [category_id]}).json()
    assert [item["name"] for item in by_category["items"]] == ["Mercado"]

    by_payment_method = client.get(
        "/api/v1/expenses/", params={"payment_method_ids": [payment_method_id]}
    ).json()
    assert [item["name"] for item in by_payment_method["items"]] == ["Mercado"]

    # Multi-seleccion: cualquiera de los ids coincide.
    by_both_categories = client.get(
        "/api/v1/expenses/", params={"category_ids": [category_id, other_category.id]}
    ).json()
    assert by_both_categories["total"] == 2

    by_tag = client.get("/api/v1/expenses/", params={"tag_ids": [tag_id]}).json()
    assert [item["name"] for item in by_tag["items"]] == ["Mercado"]

    by_amount_range = client.get(
        "/api/v1/expenses/", params={"min_amount": 10000, "max_amount": 30000}
    ).json()
    assert [item["name"] for item in by_amount_range["items"]] == ["Mercado"]

    combined = client.get(
        "/api/v1/expenses/",
        params={"category_ids": [category_id], "payment_method_ids": [payment_method_id]},
    ).json()
    assert combined["total"] == 1

    matches_neither = client.get(
        "/api/v1/expenses/",
        params={"category_ids": [category_id], "payment_method_ids": [other_payment_method.id]},
    ).json()
    assert matches_neither["total"] == 0


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


def test_summarize_expenses_groups_by_each_dimension(db_session):
    category_id, payment_method_id, tag_id = _seed_catalog(db_session)
    other_category = Category(name="Transport", icon_key="bus", color_key="sky")
    db_session.add(other_category)
    db_session.commit()

    def create(amount, recorded_on, *, category, tag_ids):
        response = client.post(
            "/api/v1/expenses/",
            json={
                "name": "Gasto",
                "amount": amount,
                "recorded_on": recorded_on,
                "payment_method_id": payment_method_id,
                "category_id": category,
                "tag_ids": tag_ids,
            },
        )
        assert response.status_code == 201

    create(10000, "2025-12-31", category=category_id, tag_ids=[tag_id])
    create(20000, "2026-01-15", category=category_id, tag_ids=[])
    create(5000, "2026-01-20", category=other_category.id, tag_ids=[tag_id])

    def summary(group_by, **params):
        response = client.get("/api/v1/expenses/summary", params={"group_by": group_by, **params})
        assert response.status_code == 200
        return response.json()

    by_category = summary("category")
    assert by_category["total"] == 35000
    assert by_category["count"] == 3
    assert [(b["label"], b["total"], b["count"]) for b in by_category["buckets"]] == [
        ("Groceries", 30000, 2),
        ("Transport", 5000, 1),
    ]
    assert by_category["buckets"][0]["color_key"] == "lime"

    by_tag = summary("tag")
    assert {b["key"]: b["total"] for b in by_tag["buckets"]} == {str(tag_id): 15000, "none": 20000}

    by_method = summary("payment_method")
    assert [(b["key"], b["total"]) for b in by_method["buckets"]] == [
        (str(payment_method_id), 35000)
    ]

    by_month = summary("month")
    assert [(b["key"], b["total"]) for b in by_month["buckets"]] == [
        ("2025-12", 10000),
        ("2026-01", 25000),
    ]

    by_year = summary("year")
    assert [(b["key"], b["count"]) for b in by_year["buckets"]] == [("2025", 1), ("2026", 2)]

    # Los filtros son los mismos del listado.
    filtered = summary("category", start_date="2026-01-01", category_ids=[category_id])
    assert filtered["total"] == 20000
    assert [b["label"] for b in filtered["buckets"]] == ["Groceries"]


def test_summarize_expenses_rejects_unknown_group_by():
    response = client.get("/api/v1/expenses/summary", params={"group_by": "weekday"})
    assert response.status_code == 422
