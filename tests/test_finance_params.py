"""Parametros de finanzas que administra cada usuario: tags, fuentes y
subcategorias de ingreso (/finances/*). Borrado hibrido, unicidad de nombres,
bloqueos que protegen registros existentes y aislamiento entre usuarios."""

from datetime import date

from app.db.models.finance import (
    Category,
    DirectIncome,
    Expense,
    IncomeSource,
    IncomeSubcategory,
    InterestIncome,
    PaymentMethod,
    Tag,
)
from tests.conftest import acting_as, client

API = "/api/v1/finances"


def _source(db_session, *, name="Salario", type_="DIRECT", user_id=1) -> IncomeSource:
    source = IncomeSource(user_id=user_id, type=type_, name=name)
    db_session.add(source)
    db_session.flush()
    return source


def _subcategory(db_session, source: IncomeSource, name="BASE") -> IncomeSubcategory:
    subcategory = IncomeSubcategory(
        user_id=source.user_id, source_id=source.id, type=source.type, name=name
    )
    db_session.add(subcategory)
    db_session.flush()
    return subcategory


def _direct_income(db_session, source, subcategory, tags=()) -> DirectIncome:
    income = DirectIncome(
        user_id=source.user_id,
        source_id=source.id,
        subcategory_id=subcategory.id,
        amount=1000,
        recorded_on=date(2026, 9, 1),
        tags=list(tags),
    )
    db_session.add(income)
    db_session.commit()
    return income


def _expense_with_tag(db_session, tag: Tag) -> None:
    category = Category(name="Groceries", icon_key="shopping-cart", color_key="lime")
    method = PaymentMethod(name="Cash", icon_key="banknote", color_key="green")
    db_session.add_all([category, method])
    db_session.flush()
    db_session.add(
        Expense(
            user_id=tag.user_id,
            name="Mercado",
            amount=1000,
            recorded_on=date(2026, 9, 1),
            category_id=category.id,
            payment_method_id=method.id,
            tags=[tag],
        )
    )
    db_session.commit()


# --- Tags ---


def test_tag_crud_with_usage_count(db_session):
    created = client.post(f"{API}/tags", json={"name": " NEEDED ", "color_key": "emerald"})
    assert created.status_code == 201
    tag = created.json()
    assert tag["name"] == "NEEDED"  # sin espacios al borde
    assert tag["status"] == "ENABLED"
    assert tag["usage_count"] == 0

    _expense_with_tag(db_session, db_session.get(Tag, tag["id"]))

    listed = client.get(f"{API}/tags").json()
    assert [(t["name"], t["usage_count"]) for t in listed] == [("NEEDED", 1)]

    updated = client.put(f"{API}/tags/{tag['id']}", json={"name": "NEED", "color_key": "teal"})
    assert updated.status_code == 200
    assert updated.json()["color_key"] == "teal"
    assert updated.json()["usage_count"] == 1


def test_tag_names_are_unique_ignoring_case_and_counting_archived(db_session):
    db_session.add(Tag(user_id=1, name="OLD", color_key="red", status="DISABLED"))
    db_session.commit()

    response = client.post(f"{API}/tags", json={"name": "old", "color_key": "red"})

    assert response.status_code == 409
    assert "archivado" in response.json()["detail"]


def test_unused_tag_is_deleted(db_session):
    tag_id = client.post(f"{API}/tags", json={"name": "X", "color_key": "red"}).json()["id"]

    response = client.delete(f"{API}/tags/{tag_id}")

    assert response.json() == {"result": "DELETED"}
    assert db_session.get(Tag, tag_id) is None


def test_used_tag_is_archived_and_can_be_restored(db_session):
    tag = Tag(user_id=1, name="NEEDED", color_key="emerald")
    db_session.add(tag)
    db_session.flush()
    source = _source(db_session)
    _direct_income(db_session, source, _subcategory(db_session, source), tags=[tag])

    assert client.delete(f"{API}/tags/{tag.id}").json() == {"result": "ARCHIVED"}
    # Archivado: no se ofrece en los formularios, pero sigue existiendo.
    assert client.get("/api/v1/expenses/options").json()["tags"] == []
    assert client.get("/api/v1/incomes/options").json()["tags"] == []

    restored = client.put(
        f"{API}/tags/{tag.id}", json={"name": "NEEDED", "color_key": "emerald", "status": "ENABLED"}
    )
    assert restored.json()["status"] == "ENABLED"


def test_another_users_tag_is_invisible_and_untouchable(db_session, other_user):
    db_session.add(Tag(user_id=other_user, name="AJENO", color_key="red"))
    db_session.commit()
    other_tag_id = db_session.query(Tag).filter_by(user_id=other_user).one().id

    assert client.get(f"{API}/tags").json() == []
    assert (
        client.put(f"{API}/tags/{other_tag_id}", json={"name": "Y", "color_key": "red"}).status_code
        == 404
    )
    assert client.delete(f"{API}/tags/{other_tag_id}").status_code == 404
    # El mismo nombre en otro usuario no choca.
    assert client.post(f"{API}/tags", json={"name": "AJENO", "color_key": "red"}).status_code == 201


# --- Fuentes ---


def test_source_crud_and_counts(db_session):
    created = client.post(f"{API}/income-sources", json={"name": "Salario", "type": "DIRECT"})
    assert created.status_code == 201
    source_id = created.json()["id"]
    client.post(f"{API}/income-subcategories", json={"name": "BASE", "source_id": source_id})

    listed = client.get(f"{API}/income-sources").json()
    assert listed == [
        {
            "id": source_id,
            "name": "Salario",
            "type": "DIRECT",
            "status": "ENABLED",
            "usage_count": 0,
            "subcategory_count": 1,
        }
    ]


def test_source_type_cannot_drop_records_that_use_it(db_session):
    source = _source(db_session, type_="DIRECT")
    _direct_income(db_session, source, _subcategory(db_session, source))

    to_interest = client.put(
        f"{API}/income-sources/{source.id}", json={"name": "Salario", "type": "INTEREST"}
    )
    to_all = client.put(
        f"{API}/income-sources/{source.id}", json={"name": "Salario", "type": "ALL"}
    )

    assert to_interest.status_code == 409
    assert to_all.status_code == 200


def test_interest_source_cannot_become_direct_with_interest_records(db_session):
    source = _source(db_session, name="Tyba", type_="INTEREST")
    subcategory = _subcategory(db_session, source, "RENDIMIENTOS")
    db_session.add(
        InterestIncome(
            user_id=1,
            source_id=source.id,
            subcategory_id=subcategory.id,
            amount=10,
            recorded_on=date(2026, 9, 1),
        )
    )
    db_session.commit()

    response = client.put(
        f"{API}/income-sources/{source.id}", json={"name": "Tyba", "type": "DIRECT"}
    )

    assert response.status_code == 409


def test_unused_source_is_deleted_with_its_subcategories(db_session):
    source = _source(db_session)
    subcategory = _subcategory(db_session, source)
    db_session.commit()
    source_id, subcategory_id = source.id, subcategory.id

    assert client.delete(f"{API}/income-sources/{source_id}").json() == {"result": "DELETED"}
    db_session.expire_all()
    assert db_session.get(IncomeSource, source_id) is None
    assert db_session.get(IncomeSubcategory, subcategory_id) is None


def test_used_source_is_archived_and_leaves_the_options(db_session):
    source = _source(db_session)
    subcategory = _subcategory(db_session, source)
    _direct_income(db_session, source, subcategory)

    assert client.delete(f"{API}/income-sources/{source.id}").json() == {"result": "ARCHIVED"}

    options = client.get("/api/v1/incomes/options").json()
    assert options["sources"] == []
    # Los registros viejos siguen mostrandola.
    item = client.get("/api/v1/incomes/direct").json()["items"][0]
    assert item["source"]["status"] == "DISABLED"


def test_archived_source_rejects_new_records_but_allows_editing_old_ones(db_session):
    source = _source(db_session)
    subcategory = _subcategory(db_session, source)
    income = _direct_income(db_session, source, subcategory)
    client.delete(f"{API}/income-sources/{source.id}")
    payload = {
        "amount": 2000,
        "recorded_on": "2026-09-02",
        "source_id": source.id,
        "subcategory_id": subcategory.id,
    }

    assert client.post("/api/v1/incomes/direct", json=payload).status_code == 404
    assert client.put(f"/api/v1/incomes/direct/{income.id}", json=payload).status_code == 200


# --- Subcategorias ---


def test_subcategory_names_are_unique_per_source(db_session):
    salary = _source(db_session, name="Salario")
    sale = _source(db_session, name="Venta")
    db_session.commit()

    first = client.post(
        f"{API}/income-subcategories", json={"name": "EXTRA", "source_id": salary.id}
    )
    same_source = client.post(
        f"{API}/income-subcategories", json={"name": "extra", "source_id": salary.id}
    )
    other_source = client.post(
        f"{API}/income-subcategories", json={"name": "EXTRA", "source_id": sale.id}
    )

    assert first.status_code == 201
    assert first.json()["type"] == "DIRECT"  # la hereda de la fuente
    assert same_source.status_code == 409
    assert other_source.status_code == 201


def test_used_subcategory_cannot_move_to_another_source(db_session):
    salary = _source(db_session, name="Salario")
    sale = _source(db_session, name="Venta")
    subcategory = _subcategory(db_session, salary, "EXTRA")
    _direct_income(db_session, salary, subcategory)

    moved = client.put(
        f"{API}/income-subcategories/{subcategory.id}", json={"name": "EXTRA", "source_id": sale.id}
    )
    renamed = client.put(
        f"{API}/income-subcategories/{subcategory.id}",
        json={"name": "EXTRAS", "source_id": salary.id},
    )

    assert moved.status_code == 409
    assert renamed.status_code == 200
    assert renamed.json()["usage_count"] == 1


def test_subcategory_hybrid_delete(db_session):
    source = _source(db_session)
    used = _subcategory(db_session, source, "USADA")
    unused = _subcategory(db_session, source, "LIBRE")
    _direct_income(db_session, source, used)

    assert client.delete(f"{API}/income-subcategories/{used.id}").json() == {"result": "ARCHIVED"}
    assert client.delete(f"{API}/income-subcategories/{unused.id}").json() == {"result": "DELETED"}
    assert [s["name"] for s in client.get("/api/v1/incomes/options").json()["subcategories"]] == []


def test_subcategory_cannot_use_another_users_source(db_session, other_user):
    with acting_as(other_user):
        other_source_id = client.post(
            f"{API}/income-sources", json={"name": "Ajena", "type": "DIRECT"}
        ).json()["id"]

    response = client.post(
        f"{API}/income-subcategories", json={"name": "X", "source_id": other_source_id}
    )

    assert response.status_code == 404
    assert client.get(f"{API}/income-sources").json() == []
