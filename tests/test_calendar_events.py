"""Pruebas de eventos de calendario: festivos/eventos generales (cld_events)
y eventos personales (cld_user_events), vistos como marcadores de
inicio/fin/dia-unico dentro de un rango (vista semanal).

El engine, el cliente y el aislamiento por test viven en conftest.py.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.cld_event import CldEvent
from app.db.models.cld_user_event import CldUserEvent
from app.main import app
from tests.conftest import client

TODAY = date.today()


def _d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def _make_category(name: str) -> int:
    current = client.get("/api/v1/checklists/categories").json()
    items = [{"id": c["id"], "name": c["name"]} for c in current] + [{"name": name}]
    updated = client.put("/api/v1/checklists/categories", json={"items": items}).json()
    return next(c["id"] for c in updated if c["name"] == name)


def _insert(db, model, **kwargs) -> None:
    """Inserta directo, para armar escenarios de lectura sin depender de los
    endpoints de escritura. `db` es la sesion del test (fixture db_session),
    que es la misma que la app usa durante ese test."""
    db.add(model(**kwargs))
    db.commit()


def test_single_day_event_gives_one_marker(db_session):
    _insert(
        db_session,
        CldEvent,
        code="HOLIDAY",
        first_day=_d(500),
        last_day=_d(500),
        name="Test holiday",
        detail=None,
    )

    response = client.get(f"/api/v1/calendar-events?first_day={_d(497)}&last_day={_d(503)}")
    assert response.status_code == 200
    matching = [m for m in response.json() if m["name"] == "Test holiday"]
    assert len(matching) == 1
    assert matching[0]["marker_type"] == "single"
    assert matching[0]["marker_date"] == _d(500).isoformat()
    assert matching[0]["source"] == "event"
    assert matching[0]["code"] == "HOLIDAY"


def test_holiday_outside_range_is_not_returned(db_session):
    _insert(
        db_session,
        CldEvent,
        code="HOLIDAY",
        first_day=_d(510),
        last_day=_d(510),
        name="Far holiday",
        detail=None,
    )

    response = client.get(f"/api/v1/calendar-events?first_day={_d(497)}&last_day={_d(503)}").json()
    assert all(m["name"] != "Far holiday" for m in response)


def test_multi_day_user_event_gives_start_and_end_markers_when_both_in_range(db_session):
    category_id = _make_category("Events test category")
    _insert(
        db_session,
        CldUserEvent,
        user_id=1,
        category_id=category_id,
        code="VACATION",
        first_day=_d(520),
        last_day=_d(524),
        name="Beach vacation",
        detail="Cartagena",
    )

    response = client.get(f"/api/v1/calendar-events?first_day={_d(518)}&last_day={_d(526)}").json()
    matching = [m for m in response if m["name"] == "Beach vacation"]
    assert len(matching) == 2
    types_by_date = {m["marker_date"]: m["marker_type"] for m in matching}
    assert types_by_date[_d(520).isoformat()] == "start"
    assert types_by_date[_d(524).isoformat()] == "end"
    assert all(m["source"] == "user_event" for m in matching)


def test_multi_day_event_gives_only_the_boundary_that_falls_in_the_requested_range(db_session):
    category_id = _make_category("Events partial overlap")
    _insert(
        db_session,
        CldUserEvent,
        user_id=1,
        category_id=category_id,
        code="TRAVEL",
        first_day=_d(530),
        last_day=_d(540),
        name="Long trip",
        detail=None,
    )

    # Semana que solo cubre el inicio del viaje
    start_week = client.get(
        f"/api/v1/calendar-events?first_day={_d(529)}&last_day={_d(535)}"
    ).json()
    start_matching = [m for m in start_week if m["name"] == "Long trip"]
    assert len(start_matching) == 1
    assert start_matching[0]["marker_type"] == "start"

    # Semana que solo cubre el final del viaje
    end_week = client.get(f"/api/v1/calendar-events?first_day={_d(538)}&last_day={_d(544)}").json()
    end_matching = [m for m in end_week if m["name"] == "Long trip"]
    assert len(end_matching) == 1
    assert end_matching[0]["marker_type"] == "end"

    # Semana intermedia, sin ninguno de los dos bordes: no aparece
    middle_week = client.get(
        f"/api/v1/calendar-events?first_day={_d(536)}&last_day={_d(536)}"
    ).json()
    assert all(m["name"] != "Long trip" for m in middle_week)


def test_ranges_endpoint_returns_the_full_span_not_just_boundaries(db_session):
    _insert(
        db_session,
        CldEvent,
        code="HOLIDAY",
        first_day=_d(550),
        last_day=_d(550),
        name="Range test holiday",
        detail=None,
    )
    category_id = _make_category("Ranges test category")
    _insert(
        db_session,
        CldUserEvent,
        user_id=1,
        category_id=category_id,
        code="TRAVEL",
        first_day=_d(560),
        last_day=_d(562),
        name="Conference",
        detail=None,
    )

    response = client.get(
        f"/api/v1/calendar-events/ranges?first_day={_d(548)}&last_day={_d(565)}"
    ).json()

    holiday = next(r for r in response if r["name"] == "Range test holiday")
    assert holiday["first_day"] == holiday["last_day"] == _d(550).isoformat()
    assert holiday["source"] == "event"
    assert holiday["code"] == "HOLIDAY"

    conference = next(r for r in response if r["name"] == "Conference")
    assert conference["first_day"] == _d(560).isoformat()
    assert conference["last_day"] == _d(562).isoformat()
    assert conference["source"] == "user_event"
    assert conference["code"] == "TRAVEL"


def test_ranges_endpoint_excludes_events_entirely_outside_the_range(db_session):
    _insert(
        db_session,
        CldEvent,
        code="HOLIDAY",
        first_day=_d(570),
        last_day=_d(570),
        name="Out of range holiday",
        detail=None,
    )

    response = client.get(
        f"/api/v1/calendar-events/ranges?first_day={_d(548)}&last_day={_d(565)}"
    ).json()
    assert all(r["name"] != "Out of range holiday" for r in response)


# --- Eventos personales: alta, edicion y borrado (cld_user_events) ---

USER_EVENTS = "/api/v1/calendar-events/user-events"


def _event_payload(category_id: int, **overrides) -> dict:
    return {
        "category_id": category_id,
        "code": "TRAVEL",
        "first_day": _d(600).isoformat(),
        "last_day": _d(602).isoformat(),
        "name": "Viaje",
        "detail": None,
        **overrides,
    }


def _ranges_around(offset: int) -> list[dict]:
    return client.get(
        f"/api/v1/calendar-events/ranges?first_day={_d(offset - 5)}&last_day={_d(offset + 5)}"
    ).json()


def test_create_user_event_shows_up_in_ranges_with_its_category():
    category_id = _make_category("Viajes CRUD")

    response = client.post(USER_EVENTS, json=_event_payload(category_id, name="Cartagena"))

    assert response.status_code == 201
    created = response.json()
    [listed] = [r for r in _ranges_around(600) if r["name"] == "Cartagena"]
    assert listed["id"] == created["id"]
    assert listed["source"] == "user_event"
    assert listed["category_id"] == category_id


def test_code_is_always_stored_in_uppercase():
    category_id = _make_category("Mayusculas")

    created = client.post(USER_EVENTS, json=_event_payload(category_id, code="  day   off ")).json()
    updated = client.put(
        f"{USER_EVENTS}/{created['id']}", json=_event_payload(category_id, code="concert")
    ).json()

    assert created["code"] == "DAY OFF"
    assert updated["code"] == "CONCERT"


def test_blank_code_is_rejected():
    category_id = _make_category("Sin tipo")

    response = client.post(USER_EVENTS, json=_event_payload(category_id, code="   "))

    assert response.status_code == 422


def test_last_day_before_first_day_is_rejected():
    category_id = _make_category("Rango invertido")

    response = client.post(
        USER_EVENTS,
        json=_event_payload(
            category_id, first_day=_d(610).isoformat(), last_day=_d(609).isoformat()
        ),
    )

    assert response.status_code == 422


def test_update_user_event_changes_every_editable_field():
    first = _make_category("Antes")
    second = _make_category("Despues")
    event_id = client.post(USER_EVENTS, json=_event_payload(first)).json()["id"]

    response = client.put(
        f"{USER_EVENTS}/{event_id}",
        json=_event_payload(
            second,
            code="VACATION",
            first_day=_d(620).isoformat(),
            last_day=_d(625).isoformat(),
            name="Playa",
            detail="Con la familia",
        ),
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": event_id,
        "category_id": second,
        "code": "VACATION",
        "first_day": _d(620).isoformat(),
        "last_day": _d(625).isoformat(),
        "name": "Playa",
        "detail": "Con la familia",
    }


def test_delete_user_event_removes_it():
    category_id = _make_category("Para borrar")
    event_id = client.post(USER_EVENTS, json=_event_payload(category_id, name="Efimero")).json()[
        "id"
    ]

    assert client.delete(f"{USER_EVENTS}/{event_id}").status_code == 204
    assert all(r["name"] != "Efimero" for r in _ranges_around(600))
    assert client.delete(f"{USER_EVENTS}/{event_id}").status_code == 404


def test_unknown_user_event_returns_404():
    category_id = _make_category("Fantasma")

    assert client.put(f"{USER_EVENTS}/999999", json=_event_payload(category_id)).status_code == 404
    assert client.delete(f"{USER_EVENTS}/999999").status_code == 404


def test_user_event_cannot_use_a_disabled_category():
    category_id = _make_category("Se deshabilita")
    current = client.get("/api/v1/checklists/categories").json()
    remaining = [{"id": c["id"], "name": c["name"]} for c in current if c["id"] != category_id]
    client.put("/api/v1/checklists/categories", json={"items": remaining})

    response = client.post(USER_EVENTS, json=_event_payload(category_id))

    assert response.status_code == 404


def test_user_event_codes_lists_each_type_once_in_order():
    category_id = _make_category("Tipos")
    for code in ("TRAVEL", "birthday", "travel"):
        client.post(USER_EVENTS, json=_event_payload(category_id, code=code))

    codes = client.get("/api/v1/calendar-events/user-event-codes").json()

    assert codes == sorted(set(codes))
    assert {"BIRTHDAY", "TRAVEL"} <= set(codes)


def test_database_rejects_a_lowercase_code(db_session):
    category_id = _make_category("Check en base")

    with pytest.raises(IntegrityError):
        _insert(
            db_session,
            CldUserEvent,
            user_id=1,
            category_id=category_id,
            code="travel",
            first_day=_d(630),
            last_day=_d(630),
            name="Directo a la base",
            detail=None,
        )
    db_session.rollback()
