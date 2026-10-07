"""Pruebas de los endpoints de ingresos (directos e intereses) y sus catalogos.

Igual que en test_expenses.py, los catalogos no los siembra
`ensure_default_user`: cada test crea las fuentes/subcategorias/tags que usa.
"""

from app.db.models.finance import IncomeSource, IncomeSubcategory, Tag
from app.db.models.user import User
from tests.conftest import client


def _seed(db_session, *, user_id: int = 1) -> dict[str, int]:
    """Fuentes con sus subcategorias: "Salario" -> SALARIO BASE / EXTRA,
    "Tyba" -> RENDIMIENTOS, "Venta" -> su propio EXTRA (mismo nombre, otra fuente)."""
    salary = IncomeSource(user_id=user_id, type="DIRECT", name="Salario")
    sale = IncomeSource(user_id=user_id, type="DIRECT", name="Venta")
    tyba = IncomeSource(user_id=user_id, type="INTEREST", name="Tyba")
    tag = Tag(user_id=user_id, name="RECURRING", color_key="violet")
    db_session.add_all([salary, sale, tyba, tag])
    db_session.flush()

    def sub(source: IncomeSource, name: str) -> IncomeSubcategory:
        return IncomeSubcategory(user_id=user_id, source_id=source.id, type=source.type, name=name)

    rows = {
        "base": sub(salary, "SALARIO BASE"),
        "extra": sub(salary, "EXTRA"),
        "sale_extra": sub(sale, "EXTRA"),
        "yield": sub(tyba, "RENDIMIENTOS"),
        # Segundo producto de la misma fuente: puede tener su propio registro mensual.
        "car": sub(tyba, "MI CARRO"),
    }
    db_session.add_all(rows.values())
    db_session.commit()
    return {
        "salary": salary.id,
        "sale": sale.id,
        "tyba": tyba.id,
        "tag": tag.id,
        **{key: row.id for key, row in rows.items()},
    }


def _direct_payload(ids: dict[str, int], **overrides) -> dict:
    return {
        "amount": 3500000.5,
        "recorded_on": "2026-09-15",
        "source_id": ids["salary"],
        "subcategory_id": ids["base"],
        "tag_ids": [ids["tag"]],
        "note": "Quincena",
        **overrides,
    }


def _interest_payload(ids: dict[str, int], **overrides) -> dict:
    return {
        "amount": 50000,
        "recorded_on": "2026-08-20",
        "start_of_month_amount": 3000000,
        "end_of_month_amount": 3550000,
        "deposits_amount": 500000,
        "withdrawals_amount": 0,
        "source_id": ids["tyba"],
        "subcategory_id": ids["yield"],
        **overrides,
    }


def test_options_return_catalogs_and_end_balances_in_one_call(db_session):
    ids = _seed(db_session)
    client.post("/api/v1/incomes/interest", json=_interest_payload(ids))

    body = client.get("/api/v1/incomes/options").json()

    assert [s["name"] for s in body["sources"]] == ["Salario", "Venta", "Tyba"]
    assert [(s["name"], s["source_id"]) for s in body["subcategories"]] == [
        ("SALARIO BASE", ids["salary"]),
        ("EXTRA", ids["salary"]),
        ("EXTRA", ids["sale"]),
        ("RENDIMIENTOS", ids["tyba"]),
        ("MI CARRO", ids["tyba"]),
    ]
    assert [t["id"] for t in body["tags"]] == [ids["tag"]]
    assert body["interest_end_balances"] == [
        {
            "source_id": ids["tyba"],
            "subcategory_id": ids["yield"],
            "period": "2026-08",
            "end_of_month_amount": 3550000,
        }
    ]


def test_create_direct_income_with_decimals_and_tags(db_session):
    ids = _seed(db_session)

    response = client.post("/api/v1/incomes/direct", json=_direct_payload(ids))

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == 3500000.5
    assert body["source"]["name"] == "Salario"
    assert body["subcategory"]["name"] == "SALARIO BASE"
    assert [t["id"] for t in body["tags"]] == [ids["tag"]]


def test_direct_income_rejects_more_than_two_decimals(db_session):
    ids = _seed(db_session)
    response = client.post("/api/v1/incomes/direct", json=_direct_payload(ids, amount=10.555))
    assert response.status_code == 422


def test_direct_income_rejects_source_of_other_kind(db_session):
    ids = _seed(db_session)
    response = client.post(
        "/api/v1/incomes/direct", json=_direct_payload(ids, source_id=ids["tyba"])
    )
    assert response.status_code == 404


def test_subcategory_must_belong_to_the_source(db_session):
    ids = _seed(db_session)
    # "EXTRA" de Venta no sirve para Salario, aunque se llame igual.
    wrong = client.post(
        "/api/v1/incomes/direct", json=_direct_payload(ids, subcategory_id=ids["sale_extra"])
    )
    right = client.post(
        "/api/v1/incomes/direct",
        json=_direct_payload(ids, source_id=ids["sale"], subcategory_id=ids["sale_extra"]),
    )
    interest_with_direct_sub = client.post(
        "/api/v1/incomes/interest", json=_interest_payload(ids, subcategory_id=ids["base"])
    )
    assert wrong.status_code == 404
    assert right.status_code == 201
    assert interest_with_direct_sub.status_code == 404


def test_list_direct_incomes_filters(db_session):
    ids = _seed(db_session)
    client.post("/api/v1/incomes/direct", json=_direct_payload(ids))
    client.post(
        "/api/v1/incomes/direct",
        json=_direct_payload(
            ids, amount=200000, recorded_on="2026-08-01", subcategory_id=ids["extra"], tag_ids=[]
        ),
    )

    all_items = client.get("/api/v1/incomes/direct").json()
    assert all_items["total"] == 2
    # Mas reciente primero.
    assert all_items["items"][0]["recorded_on"] == "2026-09-15"

    by_sub = client.get(f"/api/v1/incomes/direct?subcategory_id={ids['extra']}").json()
    assert [i["amount"] for i in by_sub["items"]] == [200000]

    by_tag = client.get(f"/api/v1/incomes/direct?tag_ids={ids['tag']}").json()
    assert by_tag["total"] == 1

    by_date = client.get("/api/v1/incomes/direct?start_date=2026-09-01").json()
    assert by_date["total"] == 1

    by_amount = client.get("/api/v1/incomes/direct?min_amount=1000000").json()
    assert by_amount["total"] == 1


def test_update_and_delete_direct_income(db_session):
    ids = _seed(db_session)
    record_id = client.post("/api/v1/incomes/direct", json=_direct_payload(ids)).json()["id"]

    updated = client.put(
        f"/api/v1/incomes/direct/{record_id}",
        json=_direct_payload(ids, amount=100, subcategory_id=ids["extra"], tag_ids=[]),
    )
    assert updated.status_code == 200
    assert updated.json()["subcategory"]["name"] == "EXTRA"
    assert updated.json()["tags"] == []
    assert updated.json()["updated_at"] is not None

    assert client.delete(f"/api/v1/incomes/direct/{record_id}").status_code == 204
    assert client.delete(f"/api/v1/incomes/direct/{record_id}").status_code == 404


def test_cannot_touch_other_users_income(db_session):
    db_session.add(User(id=2, name="Otro", email="otro@example.com", timezone="UTC"))
    db_session.commit()
    other_ids = _seed(db_session, user_id=2)
    ids = _seed(db_session)

    # Fuente ajena: no es una opcion valida para el usuario actual.
    response = client.post(
        "/api/v1/incomes/direct", json=_direct_payload(ids, source_id=other_ids["salary"])
    )
    assert response.status_code == 404
    assert client.get("/api/v1/incomes/direct").json()["total"] == 0


def test_interest_income_normalizes_period_and_allows_negative(db_session):
    ids = _seed(db_session)

    response = client.post(
        "/api/v1/incomes/interest",
        json=_interest_payload(ids, amount=-12500.25, note="Mes malo"),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["recorded_on"] == "2026-08-01"
    assert body["amount"] == -12500.25
    assert body["deposits_amount"] == 500000
    assert body["note"] == "Mes malo"


def test_interest_income_balances_are_optional(db_session):
    ids = _seed(db_session)
    payload = _interest_payload(ids)
    del payload["start_of_month_amount"], payload["end_of_month_amount"]
    del payload["deposits_amount"], payload["withdrawals_amount"]

    response = client.post("/api/v1/incomes/interest", json=payload)

    assert response.status_code == 201
    assert response.json()["start_of_month_amount"] is None
    assert response.json()["withdrawals_amount"] == 0


def test_interest_income_one_per_subcategory_and_month(db_session):
    ids = _seed(db_session)
    first = client.post("/api/v1/incomes/interest", json=_interest_payload(ids)).json()
    second = client.post(
        "/api/v1/incomes/interest", json=_interest_payload(ids, recorded_on="2026-07-01")
    ).json()

    duplicate = client.post(
        "/api/v1/incomes/interest", json=_interest_payload(ids, recorded_on="2026-08-31")
    )
    assert duplicate.status_code == 409

    # Otra subcategoria de la misma fuente (otro producto) si puede tener ese mes.
    other_product = client.post(
        "/api/v1/incomes/interest", json=_interest_payload(ids, subcategory_id=ids["car"])
    )
    assert other_product.status_code == 201

    # Editar el mismo registro sin cambiar de mes no choca consigo mismo...
    same = client.put(
        f"/api/v1/incomes/interest/{first['id']}", json=_interest_payload(ids, amount=1)
    )
    assert same.status_code == 200
    # ...pero moverlo a un mes ya ocupado si.
    moved = client.put(f"/api/v1/incomes/interest/{second['id']}", json=_interest_payload(ids))
    assert moved.status_code == 409


def test_list_and_delete_interest_income(db_session):
    ids = _seed(db_session)
    record_id = client.post("/api/v1/incomes/interest", json=_interest_payload(ids)).json()["id"]

    page = client.get("/api/v1/incomes/interest?min_amount=-100000").json()
    assert page["total"] == 1

    assert client.delete(f"/api/v1/incomes/interest/{record_id}").status_code == 204
    assert client.get("/api/v1/incomes/interest").json()["total"] == 0


# --- Resumen para analisis ---


def _summary(group_by: str, **params) -> dict:
    response = client.get("/api/v1/incomes/summary", params={"group_by": group_by, **params})
    assert response.status_code == 200
    return response.json()


def _seed_summary_data(db_session) -> dict[str, int]:
    """Salario: 1.000 (BASE, tag) en ene y 500 (EXTRA) en feb; Venta: 200 en
    feb; Tyba: interes 50 en ene y -10 en feb."""
    ids = _seed(db_session)
    posts = [
        ("direct", _direct_payload(ids, amount=1000, recorded_on="2026-01-15")),
        (
            "direct",
            _direct_payload(
                ids, amount=500, recorded_on="2026-02-15", subcategory_id=ids["extra"], tag_ids=[]
            ),
        ),
        (
            "direct",
            _direct_payload(
                ids,
                amount=200,
                recorded_on="2026-02-20",
                source_id=ids["sale"],
                subcategory_id=ids["sale_extra"],
                tag_ids=[],
            ),
        ),
        ("interest", _interest_payload(ids, amount=50, recorded_on="2026-01-01")),
        ("interest", _interest_payload(ids, amount=-10, recorded_on="2026-02-01")),
    ]
    for kind, payload in posts:
        assert client.post(f"/api/v1/incomes/{kind}", json=payload).status_code == 201
    return ids


def test_summary_by_source_sums_direct_and_interest(db_session):
    ids = _seed_summary_data(db_session)

    body = _summary("source")

    assert body["total"] == 1740
    assert body["count"] == 5
    assert body["direct_total"] == 1700
    assert body["interest_total"] == 40
    assert [(b["key"], b["total"]) for b in body["buckets"]] == [
        (str(ids["salary"]), 1500),
        (str(ids["sale"]), 200),
        (str(ids["tyba"]), 40),
    ]


def test_summary_filters_kind_sources_subcategories_and_tags(db_session):
    ids = _seed_summary_data(db_session)

    assert _summary("source", kind="interest")["total"] == 40
    both = _summary("source", source_ids=[ids["salary"], ids["sale"]])
    assert both["total"] == 1700
    assert _summary("source", subcategory_ids=[ids["extra"]])["total"] == 500
    assert _summary("source", tag_ids=[ids["tag"]])["total"] == 1000
    assert _summary("source", start_date="2026-02-01")["total"] == 690


def test_summary_by_subcategory_includes_parent_source(db_session):
    _seed_summary_data(db_session)

    buckets = _summary("subcategory")["buckets"]

    assert ("EXTRA", "Salario") in [(b["label"], b["parent_label"]) for b in buckets]
    assert ("EXTRA", "Venta") in [(b["label"], b["parent_label"]) for b in buckets]


def test_summary_by_tag_keeps_untagged_bucket(db_session):
    ids = _seed_summary_data(db_session)

    buckets = {b["key"]: b["total"] for b in _summary("tag")["buckets"]}

    # Los intereses no llevan tag en el payload de prueba; el directo de enero si.
    assert buckets[str(ids["tag"])] == 1000
    assert buckets["none"] == 500 + 200 + 50 - 10


def test_summary_by_month_stacked_by_source_and_subcategory(db_session):
    ids = _seed_summary_data(db_session)

    by_source = _summary("month", stack_by="source")
    assert by_source["stack_by"] == "source"
    feb = next(b for b in by_source["buckets"] if b["key"] == "2026-02")
    assert feb["total"] == 690
    assert {s["label"]: s["total"] for s in feb["segments"]} == {
        "Salario": 500,
        "Venta": 200,
        "Tyba": -10,
    }

    by_subcategory = _summary("year", stack_by="subcategory", source_ids=[ids["salary"]])
    assert [(b["key"], b["total"]) for b in by_subcategory["buckets"]] == [("2026", 1500)]
    assert {s["label"] for s in by_subcategory["buckets"][0]["segments"]} == {
        "SALARIO BASE",
        "EXTRA",
    }


def test_summary_ignores_stack_by_outside_time_series(db_session):
    _seed_summary_data(db_session)
    body = _summary("source", stack_by="subcategory")
    assert body["stack_by"] is None
    assert all(b["segments"] == [] for b in body["buckets"])


def test_summary_empty_and_invalid_group_by(db_session):
    _seed(db_session)
    empty = _summary("month")
    assert (empty["total"], empty["count"], empty["buckets"]) == (0, 0, [])
    response = client.get("/api/v1/incomes/summary", params={"group_by": "weekday"})
    assert response.status_code == 422
