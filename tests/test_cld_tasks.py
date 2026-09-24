"""Pruebas de tareas de calendario (cld_tasks): creacion, validacion de
fechas, y sincronizacion opcional con el checklist semanal (sin tocar nunca
el template).

El engine, el cliente y el aislamiento por test viven en conftest.py.
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo


from app.main import app
from app.services.cld_task_sync import (
    compute_occurrence_in_range,
    compute_occurrences_in_range,
    to_local,
    to_utc,
)


from tests.conftest import client


# Las semanas se validan contra hoy y contra la semana anterior (ver
# WeekService.get_next_range), asi que las fechas de los tests de sync se
# calculan relativas a hoy en vez de quedar fijas. _BASE se ajusta al lunes
# siguiente (bien lejos de hoy, para no chocar con otros tests de semanas) y
# se conserva un lunes para que los supuestos de dia de semana (jueves, etc.)
# sigan valiendo.
_BASE = date.today() + timedelta(days=100)
_BASE += timedelta(days=(8 - _BASE.isoweekday()) % 7)


def _d(offset: int) -> str:
    return (_BASE + timedelta(days=offset)).isoformat()


def _next_weekday_iso(iso_weekday: int, *, from_offset: int = 800) -> str:
    """Primera fecha con ese dia de semana ISO (1=Lunes..7=Domingo) a partir
    de _BASE + from_offset. Lejos de hoy, para no chocar con otros tests."""
    start = _BASE + timedelta(days=from_offset)
    return (start + timedelta(days=(iso_weekday - start.isoweekday()) % 7)).isoformat()


def _dt(offset: int, hour: int, minute: int) -> str:
    """Hora de pared del usuario, sin offset: es lo que espera la API (el
    backend le adjunta la zona del usuario y convierte a UTC para guardar)."""
    return f"{_d(offset)}T{hour:02d}:{minute:02d}:00"


def _make_category(name: str) -> int:
    current = client.get("/api/v1/checklists/categories").json()
    items = [{"id": c["id"], "name": c["name"]} for c in current] + [{"name": name}]
    updated = client.put("/api/v1/checklists/categories", json={"items": items}).json()
    return next(c["id"] for c in updated if c["name"] == name)


def _close_current_week_if_any():
    current = client.get("/api/v1/checklists/weeks/current").json()
    if current is None:
        return
    tasks = client.get(f"/api/v1/checklists/weeks/{current['id']}/tasks").json()
    for task in tasks:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{current['id']}/close")


# --- compute_occurrence_in_range (calculo puro, sin HTTP) ---


def test_occurrence_one_off_inside_range():
    anchor = datetime(2026, 11, 5, 7, 30, tzinfo=timezone.utc)
    result = compute_occurrence_in_range(None, anchor, date(2026, 11, 2), date(2026, 11, 8))
    assert result == date(2026, 11, 5)


def test_occurrence_one_off_outside_range_is_none():
    anchor = datetime(2026, 11, 1, 7, 30, tzinfo=timezone.utc)
    result = compute_occurrence_in_range(None, anchor, date(2026, 11, 2), date(2026, 11, 8))
    assert result is None


def test_occurrence_weekly_always_matches_the_week():
    anchor = datetime(2026, 10, 1, 7, 30, tzinfo=timezone.utc)  # jueves (isoweekday 4)
    assert anchor.isoweekday() == 4
    result = compute_occurrence_in_range("WEEKLY", anchor, date(2026, 11, 2), date(2026, 11, 8))
    assert result == date(2026, 11, 5)  # jueves de esa semana


def test_occurrence_monthly_clamps_to_last_day_of_shorter_month():
    anchor = datetime(2027, 1, 31, 20, 0, tzinfo=timezone.utc)  # 31, febrero no tiene ese dia
    result = compute_occurrence_in_range("MONTHLY", anchor, date(2027, 2, 25), date(2027, 3, 3))
    assert result == date(2027, 2, 28)


def test_occurrence_monthly_no_match_returns_none():
    anchor = datetime(2027, 1, 15, 20, 0, tzinfo=timezone.utc)
    result = compute_occurrence_in_range("MONTHLY", anchor, date(2027, 2, 25), date(2027, 3, 3))
    assert result is None


def test_occurrence_yearly_matches_day_and_month():
    anchor = datetime(2020, 12, 25, 9, 0, tzinfo=timezone.utc)
    result = compute_occurrence_in_range("YEARLY", anchor, date(2026, 12, 21), date(2026, 12, 27))
    assert result == date(2026, 12, 25)


# --- compute_occurrences_in_range (plural: rangos largos, ej. un mes) ---


def test_occurrences_weekly_repeats_every_seven_days_across_a_month():
    anchor = datetime(2026, 10, 1, 7, 30, tzinfo=timezone.utc)  # jueves
    result = compute_occurrences_in_range("WEEKLY", anchor, date(2026, 11, 1), date(2026, 11, 30))
    assert result == [date(2026, 11, 5), date(2026, 11, 12), date(2026, 11, 19), date(2026, 11, 26)]


def test_occurrences_one_off_gives_at_most_one():
    anchor = datetime(2026, 11, 5, 7, 30, tzinfo=timezone.utc)
    assert compute_occurrences_in_range(None, anchor, date(2026, 11, 1), date(2026, 11, 30)) == [date(2026, 11, 5)]
    assert compute_occurrences_in_range(None, anchor, date(2026, 12, 1), date(2026, 12, 31)) == []


def test_occurrences_monthly_gives_one_per_month_covered():
    anchor = datetime(2027, 1, 31, 20, 0, tzinfo=timezone.utc)
    result = compute_occurrences_in_range("MONTHLY", anchor, date(2027, 1, 1), date(2027, 3, 31))
    assert result == [date(2027, 1, 31), date(2027, 2, 28), date(2027, 3, 31)]


# --- duration_minutes: hora final, nunca cruza la medianoche del dia de inicio ---


def test_create_task_defaults_duration_to_sixty_minutes():
    category_id = _make_category("Duration default")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Default duration",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(600, 9, 0),
        },
    ).json()
    assert created["duration_minutes"] == 60


def test_create_task_accepts_explicit_duration():
    category_id = _make_category("Duration explicit")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Long task",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(601, 9, 0),
            "duration_minutes": 150,
        },
    ).json()
    assert created["duration_minutes"] == 150


def test_create_task_rejects_duration_that_crosses_midnight():
    category_id = _make_category("Duration crosses midnight")
    response = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Too long",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(602, 23, 30),
            "duration_minutes": 60,
        },
    )
    assert response.status_code == 422


def test_create_task_allows_duration_up_to_the_end_of_the_day():
    category_id = _make_category("Duration exact midnight")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Ends exactly at midnight",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(603, 23, 0),
            "duration_minutes": 60,
        },
    ).json()
    assert created["duration_minutes"] == 60


def test_occurrence_read_and_task_read_include_duration_minutes():
    category_id = _make_category("Duration in reads")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Duration visible",
            "importance": "STANDARD",
            "category_id": category_id,
            "scheduled_date": _dt(604, 9, 0),
            "duration_minutes": 30,
        },
    ).json()
    assert created["duration_minutes"] == 30

    occurrence = client.get(f"/api/v1/calendar-tasks?date={_d(604)}").json()
    matching = next(o for o in occurrence if o["name"] == "Duration visible")
    assert matching["duration_minutes"] == 30


def test_update_task_rejects_duration_that_crosses_midnight():
    category_id = _make_category("Duration update crosses midnight")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(605, 22, 0),
        },
    ).json()
    response = client.put(
        f"/api/v1/calendar-tasks/{created['id']}",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": category_id,
            "notify": True,
            "scheduled_date": _dt(605, 22, 0),
            "duration_minutes": 150,
        },
    )
    assert response.status_code == 422


def test_update_task_can_change_duration():
    category_id = _make_category("Duration update ok")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(606, 9, 0),
        },
    ).json()
    response = client.put(
        f"/api/v1/calendar-tasks/{created['id']}",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": category_id,
            "notify": True,
            "scheduled_date": _dt(606, 9, 0),
            "duration_minutes": 15,
        },
    )
    assert response.status_code == 200
    assert response.json()["duration_minutes"] == 15


# --- Validacion del payload de creacion ---


def test_create_task_requires_scheduled_date_without_repeat():
    category_id = _make_category("Calendar no repeat")
    response = client.post(
        "/api/v1/calendar-tasks",
        json={"name": "X", "importance": "HIGH", "category_id": category_id},
    )
    assert response.status_code == 422


def test_create_task_requires_repeat_date_with_repeat_mode():
    category_id = _make_category("Calendar repeat missing anchor")
    response = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": category_id,
            "repeat_mode": "WEEKLY",
        },
    )
    assert response.status_code == 422


def test_create_task_with_invalid_category_returns_404():
    response = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": 999999,
            "scheduled_date": "2026-11-05T07:30:00",
        },
    )
    assert response.status_code == 404


def test_create_one_off_task_without_checklist_sync():
    category_id = _make_category("Calendar plain")
    response = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Dentist",
            "importance": "STANDARD",
            "category_id": category_id,
            "scheduled_date": "2026-11-05T07:30:00",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["repeat_mode"] is None
    assert body["add_to_checklist"] is False
    assert body["notify"] is True


# --- Sincronizacion con el checklist semanal ---


def test_create_task_with_checklist_sync_adds_it_to_the_open_week_when_in_range():
    _close_current_week_if_any()
    category_id = _make_category("Calendar sync in range")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(0), "last_day": _d(6)},
    ).json()

    response = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Pay rent",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(3, 7, 30),
            "add_to_checklist": True,
        },
    )
    assert response.status_code == 201

    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    matching = [t for t in tasks if t["name"] == "Pay rent"]
    assert len(matching) == 1
    assert matching[0]["day_of_week"] == 4  # jueves

    templates = client.get("/api/v1/checklists/template/tasks").json()
    assert all(t["name"] != "Pay rent" for t in templates)

    _close_current_week_if_any()


def test_create_task_with_checklist_sync_out_of_range_is_added_on_the_next_matching_week():
    _close_current_week_if_any()
    category_id = _make_category("Calendar sync out of range")

    response = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Renew ID",
            "importance": "STANDARD",
            "category_id": category_id,
            "scheduled_date": _dt(38, 7, 30),
            "add_to_checklist": True,
        },
    )
    assert response.status_code == 201

    # La semana en curso no cubre esa fecha: no se agrega nada todavia
    week_before = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(7), "last_day": _d(13)},
    ).json()
    tasks_before = client.get(f"/api/v1/checklists/weeks/{week_before['id']}/tasks").json()
    assert all(t["name"] != "Renew ID" for t in tasks_before)
    _close_current_week_if_any()

    # La semana que si cubre esa fecha la recibe automaticamente al crearse
    week_match = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(35), "last_day": _d(41)},
    ).json()
    tasks_match = client.get(f"/api/v1/checklists/weeks/{week_match['id']}/tasks").json()
    matching = [t for t in tasks_match if t["name"] == "Renew ID"]
    assert len(matching) == 1
    assert matching[0]["day_of_week"] == 4  # jueves

    _close_current_week_if_any()


def test_create_weekly_repeating_task_is_added_to_every_new_week():
    _close_current_week_if_any()
    category_id = _make_category("Calendar weekly repeat")

    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Team sync",
            "importance": "STANDARD",
            "category_id": category_id,
            "repeat_mode": "WEEKLY",
            "repeat_date": _dt(42, 9, 0),  # lunes
            "add_to_checklist": True,
        },
    )

    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(42), "last_day": _d(48)},
    ).json()
    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    matching = [t for t in tasks if t["name"] == "Team sync"]
    assert len(matching) == 1
    assert matching[0]["day_of_week"] == 1

    _close_current_week_if_any()

    week2 = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(49), "last_day": _d(55)},
    ).json()
    tasks2 = client.get(f"/api/v1/checklists/weeks/{week2['id']}/tasks").json()
    matching2 = [t for t in tasks2 if t["name"] == "Team sync"]
    assert len(matching2) == 1
    assert matching2[0]["day_of_week"] == 1

    _close_current_week_if_any()


# --- Listado diario (ocurrencias concretas de un dia) ---


def test_list_for_day_includes_one_off_and_repeating_tasks():
    category_id = _make_category("Daily list mix")
    one_off_day = _d(200)
    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "One-off event",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(200, 9, 0),
        },
    )
    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Weekly event",
            "importance": "STANDARD",
            "category_id": category_id,
            "repeat_mode": "WEEKLY",
            "repeat_date": _dt(200, 14, 15),
        },
    )

    body = client.get(f"/api/v1/calendar-tasks?date={one_off_day}").json()
    names = {item["name"] for item in body}
    assert {"One-off event", "Weekly event"} <= names

    # occurrence_local es la hora de pared del usuario (lo que pinta el front);
    # occurrence_at es el mismo momento en UTC (America/Bogota = UTC-5).
    one_off = next(item for item in body if item["name"] == "One-off event")
    assert one_off["occurrence_local"].startswith(f"{one_off_day}T09:00")
    assert one_off["occurrence_at"].startswith(f"{one_off_day}T14:00")

    weekly = next(item for item in body if item["name"] == "Weekly event")
    assert weekly["occurrence_local"].startswith(f"{one_off_day}T14:15")
    assert weekly["occurrence_at"].startswith(f"{one_off_day}T19:15")

    other_day_body = client.get(f"/api/v1/calendar-tasks?date={_d(201)}").json()
    assert all(item["name"] not in ("One-off event", "Weekly event") for item in other_day_body)


# --- Edicion ---


def test_update_task_changes_fields_but_not_repeat_mode_or_checklist_flag():
    category_id = _make_category("Update calendar task")
    other_category_id = _make_category("Update calendar task target")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Draft",
            "importance": "STANDARD",
            "category_id": category_id,
            "scheduled_date": _dt(210, 8, 0),
        },
    ).json()

    response = client.put(
        f"/api/v1/calendar-tasks/{created['id']}",
        json={
            "name": "Final",
            "importance": "HIGH",
            "category_id": other_category_id,
            "notify": False,
            "detail": "updated detail",
            "scheduled_date": _dt(211, 10, 30),
            "duration_minutes": 45,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Final"
    assert body["importance"] == "HIGH"
    assert body["category_id"] == other_category_id
    assert body["notify"] is False
    assert body["detail"] == "updated detail"
    assert body["scheduled_date"].startswith(_dt(211, 10, 30)[:16])
    assert body["repeat_mode"] is None
    assert body["add_to_checklist"] is False


def test_update_task_rejects_repeat_date_when_task_does_not_repeat():
    category_id = _make_category("Update wrong date field")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(212, 8, 0),
        },
    ).json()

    response = client.put(
        f"/api/v1/calendar-tasks/{created['id']}",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": category_id,
            "notify": True,
            "repeat_date": _dt(213, 8, 0),
        },
    )
    assert response.status_code == 422


def test_update_unknown_task_returns_404():
    response = client.put(
        "/api/v1/calendar-tasks/999999",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": 1,
            "notify": True,
            "scheduled_date": _dt(214, 8, 0),
            "duration_minutes": 60,
        },
    )
    assert response.status_code == 404


def test_update_task_with_invalid_category_returns_404():
    category_id = _make_category("Update invalid category target")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(215, 8, 0),
        },
    ).json()
    response = client.put(
        f"/api/v1/calendar-tasks/{created['id']}",
        json={
            "name": "X",
            "importance": "HIGH",
            "category_id": 999999,
            "notify": True,
            "scheduled_date": _dt(215, 8, 0),
            "duration_minutes": 60,
        },
    )
    assert response.status_code == 404


# --- Borrado: ocurrencia unica vs. serie completa ---


def test_delete_single_occurrence_of_repeating_task_hides_only_that_day():
    category_id = _make_category("Delete single occurrence")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Recurring chore",
            "importance": "STANDARD",
            "category_id": category_id,
            "repeat_mode": "WEEKLY",
            "repeat_date": _dt(220, 8, 0),
        },
    ).json()

    day1 = _d(220)
    day2 = _d(227)

    delete_response = client.delete(f"/api/v1/calendar-tasks/{created['id']}?occurrence_date={day1}")
    assert delete_response.status_code == 204

    body_day1 = client.get(f"/api/v1/calendar-tasks?date={day1}").json()
    assert all(item["id"] != created["id"] for item in body_day1)

    body_day2 = client.get(f"/api/v1/calendar-tasks?date={day2}").json()
    assert any(item["id"] == created["id"] for item in body_day2)


def test_delete_whole_series_removes_every_occurrence():
    category_id = _make_category("Delete whole series")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Whole series",
            "importance": "STANDARD",
            "category_id": category_id,
            "repeat_mode": "WEEKLY",
            "repeat_date": _dt(230, 8, 0),
        },
    ).json()

    delete_response = client.delete(f"/api/v1/calendar-tasks/{created['id']}")
    assert delete_response.status_code == 204

    assert all(item["id"] != created["id"] for item in client.get(f"/api/v1/calendar-tasks?date={_d(230)}").json())
    assert all(item["id"] != created["id"] for item in client.get(f"/api/v1/calendar-tasks?date={_d(237)}").json())


def test_delete_unknown_task_returns_404():
    response = client.delete("/api/v1/calendar-tasks/999999")
    assert response.status_code == 404


# --- Alta retroactiva al checklist semanal ---


def test_enable_checklist_sync_adds_immediately_when_current_week_covers_the_date():
    _close_current_week_if_any()
    category_id = _make_category("Enable sync in range")
    occurrence_day = _d(300)
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Retro add",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(300, 6, 0),
        },
    ).json()
    assert created["add_to_checklist"] is False

    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(297), "last_day": _d(303)},
    ).json()

    response = client.post(
        f"/api/v1/calendar-tasks/{created['id']}/checklist?occurrence_date={occurrence_day}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["added_to_current_week"] is True
    assert body["task"]["add_to_checklist"] is True

    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    assert any(t["name"] == "Retro add" for t in tasks)

    _close_current_week_if_any()


def test_enable_checklist_sync_marks_flag_even_when_no_week_covers_the_date():
    _close_current_week_if_any()
    category_id = _make_category("Enable sync out of range")
    created = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Deferred add",
            "importance": "STANDARD",
            "category_id": category_id,
            "scheduled_date": _dt(310, 6, 0),
        },
    ).json()

    response = client.post(
        f"/api/v1/calendar-tasks/{created['id']}/checklist?occurrence_date={_d(310)}"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["added_to_current_week"] is False
    assert body["task"]["add_to_checklist"] is True

    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(307), "last_day": _d(313)},
    ).json()
    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    assert any(t["name"] == "Deferred add" for t in tasks)

    _close_current_week_if_any()


def test_enable_checklist_sync_for_unknown_task_returns_404():
    response = client.post(f"/api/v1/calendar-tasks/999999/checklist?occurrence_date={_d(320)}")
    assert response.status_code == 404


# --- Listado por rango (vista semanal): first_day/last_day en vez de date ---


def test_list_for_range_includes_occurrences_across_the_whole_range():
    category_id = _make_category("Weekly range mix")
    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Range one-off",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(400, 9, 0),
        },
    )
    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Range weekly",
            "importance": "STANDARD",
            "category_id": category_id,
            "repeat_mode": "WEEKLY",
            "repeat_date": _dt(402, 15, 0),
        },
    )

    response = client.get(f"/api/v1/calendar-tasks?first_day={_d(400)}&last_day={_d(406)}")
    assert response.status_code == 200
    names = {item["name"] for item in response.json()}
    assert {"Range one-off", "Range weekly"} <= names

    # Fuera del rango (semana siguiente): solo la que repite vuelve a aparecer
    next_week = client.get(f"/api/v1/calendar-tasks?first_day={_d(407)}&last_day={_d(413)}").json()
    next_week_names = {item["name"] for item in next_week}
    assert "Range one-off" not in next_week_names
    assert "Range weekly" in next_week_names


def test_list_requires_date_or_range():
    response = client.get("/api/v1/calendar-tasks")
    assert response.status_code == 422


def test_list_for_range_returns_every_occurrence_across_a_month_long_range():
    """A diferencia de un rango de 7 dias, un mes completo puede contener
    varias ocurrencias de una misma tarea WEEKLY (regresion del bug real
    donde compute_occurrence_in_range asumia a lo sumo una)."""
    category_id = _make_category("Monthly range weekly")
    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Every week this month",
            "importance": "STANDARD",
            "category_id": category_id,
            "repeat_mode": "WEEKLY",
            "repeat_date": _dt(700, 9, 0),
        },
    )

    response = client.get(f"/api/v1/calendar-tasks?first_day={_d(700)}&last_day={_d(727)}")
    assert response.status_code == 200
    matching = [item for item in response.json() if item["name"] == "Every week this month"]
    assert len(matching) == 4


# --- Categorias deshabilitadas ---


def test_disabled_category_hides_its_calendar_tasks():
    category_id = _make_category("Calendar visibility")
    day = _d(800)
    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Should disappear",
            "importance": "HIGH",
            "category_id": category_id,
            "scheduled_date": _dt(800, 9, 0),
        },
    )

    before = client.get(f"/api/v1/calendar-tasks?date={day}").json()
    assert any(item["name"] == "Should disappear" for item in before)

    remaining = [c for c in client.get("/api/v1/checklists/categories").json() if c["id"] != category_id]
    client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"id": c["id"], "name": c["name"]} for c in remaining]},
    )

    after = client.get(f"/api/v1/calendar-tasks?date={day}").json()
    assert all(item["name"] != "Should disappear" for item in after)


# --- Zona horaria: el dia del calendario se calcula en la zona del usuario,
# no sobre el instante UTC. Sin la conversion, una tarea de la noche se corre
# al dia siguiente (America/Bogota = UTC-5). ---

BOGOTA = ZoneInfo("America/Bogota")
MADRID = ZoneInfo("Europe/Madrid")


def test_late_evening_task_stays_on_the_same_local_day():
    """23:00 local es 04:00 UTC del dia siguiente: el dia que ve el usuario
    debe seguir siendo el suyo."""
    category_id = _make_category("TZ noche")
    day = _d(700)
    response = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Late night",
            "importance": "STANDARD",
            "category_id": category_id,
            "scheduled_date": f"{day}T23:00:00",
        },
    )
    assert response.status_code == 201

    body = client.get(f"/api/v1/calendar-tasks?date={day}").json()
    task = next(item for item in body if item["name"] == "Late night")
    assert task["occurrence_local"].startswith(f"{day}T23:00")
    # El instante guardado si cae al dia siguiente en UTC: eso es correcto.
    assert task["occurrence_at"].startswith(f"{_d(701)}T04:00")

    # Y no aparece en el dia siguiente, que es donde caia antes del arreglo.
    next_day = client.get(f"/api/v1/calendar-tasks?date={_d(701)}").json()
    assert all(item["name"] != "Late night" for item in next_day)


def test_early_morning_task_stays_on_the_same_local_day():
    """00:30 local es 05:30 UTC del mismo dia: el dia no se corre hacia atras."""
    category_id = _make_category("TZ madrugada")
    day = _d(702)
    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Early bird",
            "importance": "STANDARD",
            "category_id": category_id,
            "scheduled_date": f"{day}T00:30:00",
        },
    )
    body = client.get(f"/api/v1/calendar-tasks?date={day}").json()
    task = next(item for item in body if item["name"] == "Early bird")
    assert task["occurrence_local"].startswith(f"{day}T00:30")


def test_weekly_repeat_uses_the_local_weekday():
    """Ancla domingo 22:00 local = lunes 03:00 UTC. La serie debe repetir en
    domingo (dia 7), no en lunes."""
    category_id = _make_category("TZ semanal")
    sunday = _next_weekday_iso(7)
    client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Sunday night ritual",
            "importance": "STANDARD",
            "category_id": category_id,
            "repeat_mode": "WEEKLY",
            "repeat_date": f"{sunday}T22:00:00",
        },
    )
    body = client.get(f"/api/v1/calendar-tasks?date={sunday}").json()
    assert any(item["name"] == "Sunday night ritual" for item in body)

    following_monday = (date.fromisoformat(sunday) + timedelta(days=1)).isoformat()
    monday_body = client.get(f"/api/v1/calendar-tasks?date={following_monday}").json()
    assert all(item["name"] != "Sunday night ritual" for item in monday_body)


def test_monthly_repeat_uses_the_local_day_of_month():
    """Ancla dia 15 a las 23:30 local = dia 16 en UTC: la serie mensual debe
    caer el 15."""
    anchor = to_utc(datetime(2027, 3, 15, 23, 30), BOGOTA)
    local_anchor = to_local(anchor, BOGOTA)
    assert local_anchor.day == 15
    assert anchor.day == 16  # el instante UTC si cae el 16

    occurrences = compute_occurrences_in_range(
        "MONTHLY", local_anchor, date(2027, 4, 1), date(2027, 4, 30)
    )
    assert occurrences == [date(2027, 4, 15)]


def test_same_instant_falls_on_different_local_days_per_timezone():
    """La prueba de que la zona se usa de verdad y no quedo un default
    escondido: el mismo instante UTC cae en dias distintos segun la zona."""
    instant = datetime(2027, 5, 11, 2, 30, tzinfo=timezone.utc)
    assert to_local(instant, BOGOTA).date() == date(2027, 5, 10)  # 21:30 del 10
    assert to_local(instant, MADRID).date() == date(2027, 5, 11)  # 04:30 del 11


def test_api_rejects_dates_with_timezone_offset():
    """La API recibe hora de pared; un datetime con offset significa que el
    cliente ya convirtio por su cuenta y se rechaza."""
    category_id = _make_category("TZ rechazo")
    response = client.post(
        "/api/v1/calendar-tasks",
        json={
            "name": "Con offset",
            "importance": "STANDARD",
            "category_id": category_id,
            "scheduled_date": "2027-06-01T09:00:00Z",
        },
    )
    assert response.status_code == 422
