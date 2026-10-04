"""Parametros globales del sistema (/system/*, solo admin): categorias de
gasto, metodos de pago y eventos generales del calendario (festivos)."""

from datetime import date

import pytest

from app.api.deps import get_holiday_provider
from app.core.config import settings
from app.db.models.cld_event import CldEvent
from app.db.models.finance import Category, Expense, PaymentMethod
from app.integrations.holiday_provider import OfficialHoliday
from app.main import app
from tests.conftest import client

API = "/api/v1/system"


class FakeHolidays:
    """Lista fija: el test no depende de la version de la libreria."""

    country = "CO"

    def for_year(self, year: int) -> list[OfficialHoliday]:
        return [
            OfficialHoliday(day=date(year, 1, 1), name="Año Nuevo"),
            OfficialHoliday(day=date(year, 7, 20), name="Día de la Independencia"),
        ]


@pytest.fixture(autouse=True)
def as_admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "ruben@example.com")
    app.dependency_overrides[get_holiday_provider] = FakeHolidays


def test_non_admin_gets_403(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "otra@example.com")

    assert client.get(f"{API}/payment-methods").status_code == 403
    assert (
        client.post(f"{API}/calendar-events/import-holidays", json={"year": 2027}).status_code
        == 403
    )


def test_access_info_builds_the_google_link(monkeypatch):
    monkeypatch.setattr(settings, "google_cloud_project", "ulm-prod")

    body = client.get(f"{API}/access").json()

    assert (
        body["google_audience_url"]
        == "https://console.cloud.google.com/auth/audience?project=ulm-prod"
    )
    assert body["registration_mode"] == settings.registration_mode


# --- Categorias y metodos de pago ---


@pytest.mark.parametrize("path", ["expense-categories", "payment-methods"])
def test_icon_catalog_crud(path):
    payload = {"name": "Pets", "icon_key": "paw-print", "color_key": "amber"}

    created = client.post(f"{API}/{path}", json=payload)
    assert created.status_code == 201
    item_id = created.json()["id"]
    assert client.post(f"{API}/{path}", json={**payload, "name": "PETS"}).status_code == 409

    updated = client.put(
        f"{API}/{path}/{item_id}", json={**payload, "icon_key": "dog", "color_key": "teal"}
    )
    assert updated.json()["icon_key"] == "dog"
    assert [i["name"] for i in client.get(f"{API}/{path}").json()] == ["Pets"]

    assert client.delete(f"{API}/{path}/{item_id}").json() == {"result": "DELETED"}
    assert client.get(f"{API}/{path}").json() == []


def test_category_used_by_any_user_is_archived(db_session, other_user):
    category = Category(name="Groceries", icon_key="shopping-cart", color_key="lime")
    method = PaymentMethod(name="Cash", icon_key="banknote", color_key="green")
    db_session.add_all([category, method])
    db_session.flush()
    # El gasto es de OTRO usuario: igual cuenta, el catalogo es global.
    db_session.add(
        Expense(
            user_id=other_user,
            name="Mercado",
            amount=1000,
            recorded_on=date(2026, 9, 1),
            category_id=category.id,
            payment_method_id=method.id,
        )
    )
    db_session.commit()

    assert client.get(f"{API}/expense-categories").json()[0]["usage_count"] == 1
    assert client.delete(f"{API}/expense-categories/{category.id}").json() == {"result": "ARCHIVED"}
    assert client.delete(f"{API}/payment-methods/{method.id}").json() == {"result": "ARCHIVED"}

    options = client.get("/api/v1/expenses/options").json()
    assert options["categories"] == []
    assert options["payment_methods"] == []


def test_archived_category_rejects_new_expenses(db_session):
    category = Category(name="Old", icon_key="package", color_key="slate", status="DISABLED")
    method = PaymentMethod(name="Cash", icon_key="banknote", color_key="green")
    db_session.add_all([category, method])
    db_session.commit()

    response = client.post(
        "/api/v1/expenses/",
        json={
            "name": "X",
            "amount": 1000,
            "recorded_on": "2026-09-01",
            "category_id": category.id,
            "payment_method_id": method.id,
        },
    )

    assert response.status_code == 404


# --- Eventos generales del calendario ---


def test_year_view_matches_official_holidays_by_day(db_session):
    db_session.add_all(
        [
            # Cargado antes con otro nombre: igual cuenta como agregado.
            CldEvent(
                code="HOLIDAY",
                first_day=date(2027, 1, 1),
                last_day=date(2027, 1, 1),
                name="Año nuevo",
            ),
            CldEvent(
                code="SPECIAL_DATE",
                first_day=date(2027, 7, 20),
                last_day=date(2027, 7, 20),
                name="No es festivo",
            ),
            CldEvent(
                code="HOLIDAY",
                first_day=date(2026, 7, 20),
                last_day=date(2026, 7, 20),
                name="Otro año",
            ),
        ]
    )
    db_session.commit()

    body = client.get(f"{API}/calendar-events", params={"year": 2027}).json()

    assert body["country"] == "CO"
    assert [e["name"] for e in body["events"]] == ["Año nuevo", "No es festivo"]
    official = {h["name"]: h["event_id"] for h in body["official_holidays"]}
    assert official["Año Nuevo"] is not None
    # Un SPECIAL_DATE ese dia no cuenta como el festivo.
    assert official["Día de la Independencia"] is None


def test_import_adds_only_the_missing_holidays(db_session):
    db_session.add(
        CldEvent(code="HOLIDAY", first_day=date(2027, 1, 1), last_day=date(2027, 1, 1), name="Mio")
    )
    db_session.commit()

    body = client.post(f"{API}/calendar-events/import-holidays", json={"year": 2027}).json()

    assert [(e["name"], e["code"]) for e in body["events"]] == [
        ("Mio", "HOLIDAY"),
        ("Día de la Independencia", "HOLIDAY"),
    ]
    assert all(h["event_id"] is not None for h in body["official_holidays"])


def test_calendar_event_crud():
    payload = {
        "code": "SPECIAL_DATE",
        "first_day": "2027-05-09",
        "last_day": "2027-05-09",
        "name": "Día de la Madre",
    }

    created = client.post(f"{API}/calendar-events", json=payload)
    assert created.status_code == 201
    event_id = created.json()["id"]

    updated = client.put(
        f"{API}/calendar-events/{event_id}", json={**payload, "last_day": "2027-05-10"}
    )
    assert updated.json()["last_day"] == "2027-05-10"

    assert client.delete(f"{API}/calendar-events/{event_id}").status_code == 204
    assert client.delete(f"{API}/calendar-events/{event_id}").status_code == 404


def test_calendar_event_validation():
    base = {"code": "HOLIDAY", "first_day": "2027-05-09", "last_day": "2027-05-08", "name": "X"}

    assert client.post(f"{API}/calendar-events", json=base).status_code == 422
    assert (
        client.post(
            f"{API}/calendar-events", json={**base, "last_day": "2027-05-09", "code": "OTRO"}
        ).status_code
        == 422
    )
