"""Pruebas de categorias y tareas de template de checklist.

El engine, el cliente y el aislamiento por test viven en conftest.py.
"""

from datetime import date, timedelta


from app.db.models.checklist import ChecklistWeek, ChecklistWeekCategoryDayScore
from app.main import app


from tests.conftest import client


# Las semanas se validan contra la fecha real de hoy (WeekService.get_next_range),
# asi que los rangos de las pruebas se calculan relativos a ella en vez de
# quedar fijos a una fecha (lo que las volveria invalidas con el paso del tiempo).
TODAY = date.today()


def _d(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


def _reset_categories():
    """Deja las categorias del usuario en un estado conocido antes de cada test."""
    current = client.get("/api/v1/checklists/categories").json()
    client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"id": c["id"], "name": c["name"]} for c in current]},
    )


# --- Categorias ---


def test_create_categories_via_replace():
    response = client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"name": "Health"}, {"name": "Personal"}]},
    )
    assert response.status_code == 200
    body = response.json()
    assert [c["name"] for c in body] == ["Health", "Personal"]
    assert [c["priority"] for c in body] == [1, 2]


def test_reorder_and_rename_categories():
    created = client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"name": "A"}, {"name": "B"}]},
    ).json()
    a_id = next(c["id"] for c in created if c["name"] == "A")
    b_id = next(c["id"] for c in created if c["name"] == "B")

    reordered = client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"id": b_id, "name": "B renamed"}, {"id": a_id, "name": "A"}]},
    )
    assert reordered.status_code == 200
    body = reordered.json()
    assert body[0]["id"] == b_id
    assert body[0]["name"] == "B renamed"
    assert body[0]["priority"] == 1
    assert body[1]["id"] == a_id
    assert body[1]["priority"] == 2


def test_delete_category_without_tasks():
    created = client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"name": "Temp"}, {"name": "Keep"}]},
    ).json()
    temp_id = next(c["id"] for c in created if c["name"] == "Temp")
    keep_id = next(c["id"] for c in created if c["name"] == "Keep")

    response = client.put(
        "/api/v1/checklists/categories", json={"items": [{"id": keep_id, "name": "Keep"}]}
    )
    assert response.status_code == 200
    assert [c["id"] for c in response.json()] == [keep_id]


def test_delete_category_with_tasks_is_blocked():
    created = client.put(
        "/api/v1/checklists/categories", json={"items": [{"name": "InUse"}]}
    ).json()
    category_id = created[0]["id"]

    client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "Gym", "importance": "HIGH", "category_id": category_id, "days": [1]},
    )

    response = client.put("/api/v1/checklists/categories", json={"items": []})
    assert response.status_code == 409

    _reset_categories()


def test_replace_categories_rejects_unknown_id():
    response = client.put(
        "/api/v1/checklists/categories", json={"items": [{"id": 999999, "name": "Ghost"}]}
    )
    assert response.status_code == 404


# --- Template tasks ---


def _make_category(name: str) -> int:
    current = client.get("/api/v1/checklists/categories").json()
    items = [{"id": c["id"], "name": c["name"]} for c in current] + [{"name": name}]
    updated = client.put("/api/v1/checklists/categories", json={"items": items}).json()
    return next(c["id"] for c in updated if c["name"] == name)


def test_create_multi_day_task_and_list():
    category_id = _make_category("Health for tasks")

    response = client.post(
        "/api/v1/checklists/template/tasks",
        json={
            "name": "Drink water",
            "importance": "STANDARD",
            "category_id": category_id,
            "days": [5, 1, 2],
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["days"] == [1, 2, 5]
    assert body["points"] == 1

    listed = client.get("/api/v1/checklists/template/tasks").json()
    assert any(t["id"] == body["id"] and t["days"] == [1, 2, 5] for t in listed)


def test_create_task_rejects_duplicate_days():
    category_id = _make_category("Dup days")
    response = client.post(
        "/api/v1/checklists/template/tasks",
        json={
            "name": "Dup",
            "importance": "HIGH",
            "category_id": category_id,
            "days": [1, 1],
        },
    )
    assert response.status_code == 422


def test_create_task_with_invalid_category_returns_404():
    response = client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": 999999, "days": [1]},
    )
    assert response.status_code == 404


def test_high_importance_gives_two_points():
    category_id = _make_category("Points test")
    response = client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "Gym", "importance": "HIGH", "category_id": category_id, "days": [3]},
    )
    assert response.json()["points"] == 2


def test_editing_task_for_one_day_only_splits_that_day():
    category_id = _make_category("Split edit")
    created = client.post(
        "/api/v1/checklists/template/tasks",
        json={
            "name": "Stretch",
            "importance": "HIGH",
            "category_id": category_id,
            "days": [1, 2, 3],
        },
    ).json()
    task_id = created["id"]

    edited = client.put(
        f"/api/v1/checklists/template/tasks/{task_id}",
        params={"day": 2},
        json={"name": "Stretch (longer)", "importance": "STANDARD", "category_id": category_id},
    )
    assert edited.status_code == 200
    edited_body = edited.json()
    assert edited_body["id"] != task_id
    assert edited_body["days"] == [2]
    assert edited_body["name"] == "Stretch (longer)"
    assert edited_body["importance"] == "STANDARD"

    tasks = client.get("/api/v1/checklists/template/tasks").json()
    original = next(t for t in tasks if t["id"] == task_id)
    assert original["days"] == [1, 3]
    assert original["name"] == "Stretch"
    assert original["importance"] == "HIGH"


def test_editing_single_day_task_updates_in_place():
    category_id = _make_category("Single day edit")
    created = client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "Read", "importance": "HIGH", "category_id": category_id, "days": [4]},
    ).json()
    task_id = created["id"]

    edited = client.put(
        f"/api/v1/checklists/template/tasks/{task_id}",
        params={"day": 4},
        json={"name": "Read 20min", "importance": "STANDARD", "category_id": category_id},
    )
    assert edited.status_code == 200
    body = edited.json()
    assert body["id"] == task_id
    assert body["days"] == [4]
    assert body["name"] == "Read 20min"


def test_editing_wrong_day_returns_404():
    category_id = _make_category("Wrong day")
    created = client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "Task", "importance": "HIGH", "category_id": category_id, "days": [1]},
    ).json()

    response = client.put(
        f"/api/v1/checklists/template/tasks/{created['id']}",
        params={"day": 5},
        json={"name": "Task", "importance": "HIGH", "category_id": category_id},
    )
    assert response.status_code == 404


def test_deleting_task_for_one_day_only_removes_that_day():
    category_id = _make_category("Split delete")
    created = client.post(
        "/api/v1/checklists/template/tasks",
        json={
            "name": "Meditate",
            "importance": "STANDARD",
            "category_id": category_id,
            "days": [6, 7],
        },
    ).json()
    task_id = created["id"]

    response = client.delete(
        f"/api/v1/checklists/template/tasks/{task_id}", params={"day": 6}
    )
    assert response.status_code == 204

    tasks = client.get("/api/v1/checklists/template/tasks").json()
    remaining = next(t for t in tasks if t["id"] == task_id)
    assert remaining["days"] == [7]


def test_deleting_last_day_removes_the_task():
    category_id = _make_category("Delete last day")
    created = client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "Journal", "importance": "HIGH", "category_id": category_id, "days": [3]},
    ).json()
    task_id = created["id"]

    response = client.delete(
        f"/api/v1/checklists/template/tasks/{task_id}", params={"day": 3}
    )
    assert response.status_code == 204

    tasks = client.get("/api/v1/checklists/template/tasks").json()
    assert all(t["id"] != task_id for t in tasks)


# --- Semanas y tareas concretas ---


def test_get_current_week_is_none_initially():
    response = client.get("/api/v1/checklists/weeks/current")
    assert response.status_code == 200
    assert response.json() is None


def test_next_range_before_any_week_uses_seven_days_back():
    response = client.get("/api/v1/checklists/weeks/next-range")
    assert response.status_code == 200
    body = response.json()
    assert body["min_first_day"] == _d(-7)
    assert body["min_last_day"] == _d(0)


def test_create_week_rejects_more_than_seven_days():
    response = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(0), "last_day": _d(7)},
    )
    assert response.status_code == 422


def _open_week_with_template_tasks() -> tuple[int, int]:
    """Categoria + template (Gym dias 1 y 3, Water dia 1) + semana abierta que
    los copia. Devuelve (week_id, category_id).

    Cada test que necesita una semana abierta arma sus propias precondiciones:
    antes las heredaba del test anterior, lo que los volvia dependientes del
    orden de ejecucion."""
    category_id = _make_category("Weeks test")
    client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "Gym", "importance": "HIGH", "category_id": category_id, "days": [1, 3]},
    )
    client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "Water", "importance": "STANDARD", "category_id": category_id, "days": [1]},
    )
    week = client.post(
        "/api/v1/checklists/weeks", json={"first_day": _d(0), "last_day": _d(6)}
    ).json()
    return week["id"], category_id


def _create_and_close_week(first_day: str, last_day: str) -> int:
    """Semana cerrada (todas sus tareas marcadas FAILED para poder cerrarla)."""
    week = client.post(
        "/api/v1/checklists/weeks", json={"first_day": first_day, "last_day": last_day}
    ).json()
    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")
    return week["id"]


def test_create_week_copies_template_tasks_split_by_day():
    category_id = _make_category("Weeks test")
    client.post(
        "/api/v1/checklists/template/tasks",
        json={
            "name": "Gym",
            "importance": "HIGH",
            "category_id": category_id,
            "days": [1, 3],
        },
    )
    client.post(
        "/api/v1/checklists/template/tasks",
        json={
            "name": "Water",
            "importance": "STANDARD",
            "category_id": category_id,
            "days": [1],
        },
    )

    response = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(0), "last_day": _d(6)},
    )
    assert response.status_code == 201
    week = response.json()
    assert week["closed"] is False
    assert week["score"] is None

    current = client.get("/api/v1/checklists/weeks/current").json()
    assert current["id"] == week["id"]

    all_tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    # el template acumula tareas de tests anteriores; nos quedamos solo con
    # las de esta categoria para verificar el split por dia
    tasks = [t for t in all_tasks if t["category_id"] == category_id]
    assert len(tasks) == 3
    assert all(t["status"] == "PENDING" for t in tasks)
    day1_tasks = [t for t in tasks if t["day_of_week"] == 1]
    day3_tasks = [t for t in tasks if t["day_of_week"] == 3]
    assert {t["name"] for t in day1_tasks} == {"Gym", "Water"}
    assert {t["name"] for t in day3_tasks} == {"Gym"}


def test_create_week_blocked_while_one_is_open():
    _open_week_with_template_tasks()
    response = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(7), "last_day": _d(13)},
    )
    assert response.status_code == 409


def test_close_week_blocked_while_tasks_are_pending():
    week_id, _ = _open_week_with_template_tasks()
    tasks = client.get(f"/api/v1/checklists/weeks/{week_id}/tasks").json()
    assert any(t["status"] == "PENDING" for t in tasks)

    response = client.post(f"/api/v1/checklists/weeks/{week_id}/close")
    assert response.status_code == 409


def test_update_status_and_close_week_computes_score():
    week_id, _ = _open_week_with_template_tasks()
    tasks = client.get(f"/api/v1/checklists/weeks/{week_id}/tasks").json()

    gym_day1 = next(t for t in tasks if t["name"] == "Gym" and t["day_of_week"] == 1)

    # Cerrar exige que no quede ninguna tarea PENDING: marcamos todo FAILED y
    # despues destacamos una sola como COMPLETE, para probar que el puntaje
    # solo suma las tareas completadas.
    for task in tasks:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    completed = client.patch(
        f"/api/v1/checklists/tasks/{gym_day1['id']}", json={"status": "COMPLETE"}
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETE"

    closed = client.post(f"/api/v1/checklists/weeks/{week_id}/close")
    assert closed.status_code == 200
    closed_body = closed.json()
    assert closed_body["closed"] is True
    assert closed_body["closed_date"] is not None
    # Solo el Gym HIGH completado suma: 2 puntos. El resto quedo FAILED.
    assert closed_body["score"] == 2

    assert client.get("/api/v1/checklists/weeks/current").json() is None


def test_cannot_modify_tasks_of_a_closed_week():
    current = client.get("/api/v1/checklists/weeks/current").json()
    assert current is None  # la semana anterior ya quedo cerrada

    category_id = _make_category("Closed week guard")
    client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "Read", "importance": "HIGH", "category_id": category_id, "days": [2]},
    )
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(14), "last_day": _d(20)},
    ).json()

    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    for task in tasks:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "COMPLETE"})

    close_response = client.post(f"/api/v1/checklists/weeks/{week['id']}/close")
    assert close_response.status_code == 200

    task_id = tasks[0]["id"]
    response = client.patch(
        f"/api/v1/checklists/tasks/{task_id}", json={"status": "COMPLETE"}
    )
    assert response.status_code == 409


def test_close_week_twice_returns_409():
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(21), "last_day": _d(27)},
    ).json()
    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    for task in tasks:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "COMPLETE"})

    first_close = client.post(f"/api/v1/checklists/weeks/{week['id']}/close")
    assert first_close.status_code == 200

    second_close = client.post(f"/api/v1/checklists/weeks/{week['id']}/close")
    assert second_close.status_code == 409


def test_close_unknown_week_returns_404():
    response = client.post("/api/v1/checklists/weeks/999999/close")
    assert response.status_code == 404


def test_update_status_for_unknown_task_returns_404():
    response = client.patch(
        "/api/v1/checklists/tasks/999999", json={"status": "COMPLETE"}
    )
    assert response.status_code == 404


# --- Tareas circunstanciales (agregadas directo a la semana, sin template) ---


def test_create_ad_hoc_task_on_current_week():
    category_id = _make_category("Ad hoc tasks")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(28), "last_day": _d(34)},
    ).json()

    template_before = len(client.get("/api/v1/checklists/template/tasks").json())

    response = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={
            "name": "Fix a one-off issue",
            "importance": "HIGH",
            "category_id": category_id,
            "day_of_week": 3,
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Fix a one-off issue"
    assert body["day_of_week"] == 3
    assert body["status"] == "PENDING"
    assert body["points"] == 2

    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    assert any(t["id"] == body["id"] for t in tasks)

    # No debe crear ni modificar tareas de template
    template_after = len(client.get("/api/v1/checklists/template/tasks").json())
    assert template_after == template_before

    for task in tasks:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")


def test_create_ad_hoc_task_with_invalid_category_returns_404():
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(35), "last_day": _d(41)},
    ).json()

    response = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": 999999, "day_of_week": 1},
    )
    assert response.status_code == 404

    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    for task in tasks:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")


# --- Validaciones de rango contra la semana anterior y contra hoy ---


def test_create_week_shorter_than_seven_days_is_allowed():
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(42), "last_day": _d(44)},
    )
    assert week.status_code == 201
    body = week.json()

    tasks = client.get(f"/api/v1/checklists/weeks/{body['id']}/tasks").json()
    for task in tasks:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{body['id']}/close")


def test_next_range_reflects_the_previous_week():
    _create_and_close_week(_d(42), _d(44))
    response = client.get("/api/v1/checklists/weeks/next-range")
    assert response.status_code == 200
    body = response.json()
    assert body["min_first_day"] == _d(45)
    assert body["min_last_day"] == _d(0)


def test_create_week_rejects_start_before_previous_week_end():
    _create_and_close_week(_d(42), _d(44))
    response = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(44), "last_day": _d(50)},
    )
    assert response.status_code == 422


def test_create_week_rejects_end_before_today():
    response = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(-10), "last_day": _d(-5)},
    )
    assert response.status_code == 422


def test_create_ad_hoc_task_on_closed_week_returns_409():
    category_id = _make_category("Ad hoc closed guard")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(45), "last_day": _d(51)},
    ).json()
    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    for task in tasks:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")

    response = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={
            "name": "Too late",
            "importance": "HIGH",
            "category_id": category_id,
            "day_of_week": 1,
        },
    )
    assert response.status_code == 409


def test_create_ad_hoc_task_on_unknown_week_returns_404():
    response = client.post(
        "/api/v1/checklists/weeks/999999/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": 1, "day_of_week": 1},
    )
    assert response.status_code == 404


# --- Editar/eliminar una tarea de semana (modo Edit del checklist) ---


def test_update_task_changes_name_importance_and_category():
    category_id = _make_category("Edit mode source")
    other_category_id = _make_category("Edit mode target")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(52), "last_day": _d(58)},
    ).json()
    created = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={
            "name": "Draft name",
            "importance": "STANDARD",
            "category_id": category_id,
            "day_of_week": 2,
        },
    ).json()

    response = client.put(
        f"/api/v1/checklists/tasks/{created['id']}",
        json={"name": "Final name", "importance": "HIGH", "category_id": other_category_id},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert body["name"] == "Final name"
    assert body["importance"] == "HIGH"
    assert body["points"] == 2
    assert body["category_id"] == other_category_id
    assert body["day_of_week"] == 2  # el dia no cambia al editar

    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")


def test_update_task_with_invalid_category_returns_404():
    category_id = _make_category("Edit invalid category")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(59), "last_day": _d(65)},
    ).json()
    created = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": category_id, "day_of_week": 1},
    ).json()

    response = client.put(
        f"/api/v1/checklists/tasks/{created['id']}",
        json={"name": "X", "importance": "HIGH", "category_id": 999999},
    )
    assert response.status_code == 404

    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")


def test_update_unknown_task_returns_404():
    response = client.put(
        "/api/v1/checklists/tasks/999999",
        json={"name": "X", "importance": "HIGH", "category_id": 1},
    )
    assert response.status_code == 404


def test_update_task_on_closed_week_returns_409():
    category_id = _make_category("Edit closed guard")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(66), "last_day": _d(72)},
    ).json()
    created = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": category_id, "day_of_week": 1},
    ).json()
    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")

    response = client.put(
        f"/api/v1/checklists/tasks/{created['id']}",
        json={"name": "Y", "importance": "HIGH", "category_id": category_id},
    )
    assert response.status_code == 409


def test_delete_task_removes_it_without_confirmation():
    category_id = _make_category("Delete mode")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(73), "last_day": _d(79)},
    ).json()
    created = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={"name": "Delete me", "importance": "HIGH", "category_id": category_id, "day_of_week": 4},
    ).json()

    response = client.delete(f"/api/v1/checklists/tasks/{created['id']}")
    assert response.status_code == 204

    remaining = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    assert all(t["id"] != created["id"] for t in remaining)

    for task in remaining:
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")


def test_delete_unknown_task_returns_404():
    response = client.delete("/api/v1/checklists/tasks/999999")
    assert response.status_code == 404


def test_delete_task_on_closed_week_returns_409():
    category_id = _make_category("Delete closed guard")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(80), "last_day": _d(86)},
    ).json()
    created = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": category_id, "day_of_week": 1},
    ).json()
    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")

    response = client.delete(f"/api/v1/checklists/tasks/{created['id']}")
    assert response.status_code == 409


# --- Detalle (descripcion) de tareas ---


def test_create_template_task_without_detail_defaults_to_none():
    category_id = _make_category("Detail defaults")
    response = client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "No detail", "importance": "HIGH", "category_id": category_id, "days": [1]},
    )
    assert response.json()["detail"] is None


def test_create_and_edit_template_task_detail():
    category_id = _make_category("Detail template")
    created = client.post(
        "/api/v1/checklists/template/tasks",
        json={
            "name": "Gym",
            "importance": "HIGH",
            "category_id": category_id,
            "days": [1],
            "detail": "3 sets of squats, 3 of deadlifts",
        },
    ).json()
    assert created["detail"] == "3 sets of squats, 3 of deadlifts"

    edited = client.put(
        f"/api/v1/checklists/template/tasks/{created['id']}",
        params={"day": 1},
        json={
            "name": "Gym",
            "importance": "HIGH",
            "category_id": category_id,
            "detail": "Updated routine",
        },
    ).json()
    assert edited["detail"] == "Updated routine"


def test_editing_multi_day_template_task_keeps_original_detail_on_untouched_day():
    category_id = _make_category("Detail split")
    created = client.post(
        "/api/v1/checklists/template/tasks",
        json={
            "name": "Stretch",
            "importance": "HIGH",
            "category_id": category_id,
            "days": [1, 2],
            "detail": "Original detail",
        },
    ).json()

    edited = client.put(
        f"/api/v1/checklists/template/tasks/{created['id']}",
        params={"day": 2},
        json={
            "name": "Stretch",
            "importance": "HIGH",
            "category_id": category_id,
            "detail": "New detail for day 2",
        },
    ).json()
    assert edited["detail"] == "New detail for day 2"

    tasks = client.get("/api/v1/checklists/template/tasks").json()
    original = next(t for t in tasks if t["id"] == created["id"])
    assert original["detail"] == "Original detail"


def test_create_and_edit_week_task_detail():
    category_id = _make_category("Detail week task")
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": _d(87), "last_day": _d(93)},
    ).json()

    created = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={
            "name": "Call the dentist",
            "importance": "STANDARD",
            "category_id": category_id,
            "day_of_week": 1,
            "detail": "Ask about the appointment on Friday",
        },
    ).json()
    assert created["detail"] == "Ask about the appointment on Friday"

    edited = client.put(
        f"/api/v1/checklists/tasks/{created['id']}",
        json={
            "name": "Call the dentist",
            "importance": "STANDARD",
            "category_id": category_id,
            "detail": "Rescheduled to Monday",
        },
    ).json()
    assert edited["detail"] == "Rescheduled to Monday"

    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")


# --- Analytics (tendencias de semanas cerradas) ---
#
# Las 2 semanas reales de aca abajo usan _d(94) y _d(95) (semanas de 1 solo
# dia, a proposito): test_cld_tasks.py reserva desde _d(100) en adelante para
# sus propias semanas (ver su comentario sobre _BASE), asi que no hay que
# extender esta cadena mas alla de _d(99) sin revisar ese margen.


def test_close_week_populates_category_day_scores():
    category_id = _make_category("Score table check")
    week = client.post(
        "/api/v1/checklists/weeks", json={"first_day": _d(94), "last_day": _d(94)}
    ).json()
    created = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={"name": "One-off", "importance": "HIGH", "category_id": category_id, "day_of_week": 1},
    ).json()
    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        status = "COMPLETE" if task["id"] == created["id"] else "FAILED"
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": status})
    closed = client.post(f"/api/v1/checklists/weeks/{week['id']}/close").json()
    assert closed["score"] == 2

    year = int(closed["first_day"][:4])
    analytics = client.get("/api/v1/checklists/analytics/weekly", params={"year": year}).json()
    point = next(w for w in analytics["weeks"] if w["week_id"] == week["id"])
    assert point["first_day"] == week["first_day"]
    assert point["last_day"] == week["last_day"]
    # No afirmamos en que columna cae el puntaje: este archivo acumula
    # categorias de tests anteriores, asi que esta puede terminar agrupada en
    # "Others" (comportamiento correcto, ver MAX_NAMED_CATEGORIES). Lo que
    # importa es que el puntaje calculado al cerrar llega completo a la vista.
    assert sum(point["scores"]) == 2


def test_disabled_category_keeps_its_history_in_analytics(db_session):
    """Una categoria deshabilitada desaparece de /categories pero su
    historia sigue viva en analytics. Usa un anio sintetico propio (via
    insercion directa) para no depender de ganarle el ranking de puntaje a
    las decenas de categorias que este archivo acumula en el anio real."""
    category_id = _make_category("History after disable")
    year = 2016

    week = ChecklistWeek(
        user_id=1,
        first_day=date(year, 1, 1),
        last_day=date(year, 1, 7),
        closed=True,
        closed_date=None,
        score=7,
    )
    db_session.add(week)
    db_session.flush()
    db_session.add(
        ChecklistWeekCategoryDayScore(
            cl_week_id=week.id, category_id=category_id, day_of_week=1, score=7, points_possible=7
        )
    )
    db_session.commit()

    # Deshabilitar (hoy es lo que hace "eliminar" una categoria desde el PUT
    # de reemplazo): desaparece de la lista de categorias activas.
    remaining = [c for c in client.get("/api/v1/checklists/categories").json() if c["id"] != category_id]
    client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"id": c["id"], "name": c["name"]} for c in remaining]},
    )
    listed_ids = {c["id"] for c in client.get("/api/v1/checklists/categories").json()}
    assert category_id not in listed_ids

    analytics = client.get("/api/v1/checklists/analytics/weekly", params={"year": year}).json()
    names = {c["category_id"]: c["name"] for c in analytics["categories"]}
    assert names.get(category_id) == "History after disable"
    assert analytics["weeks"][0]["scores"] == [7]


def test_disabled_category_cannot_be_assigned_to_new_work():
    category_id = _make_category("Will be disabled")
    remaining = [c for c in client.get("/api/v1/checklists/categories").json() if c["id"] != category_id]
    client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"id": c["id"], "name": c["name"]} for c in remaining]},
    )

    template_response = client.post(
        "/api/v1/checklists/template/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": category_id, "days": [1]},
    )
    assert template_response.status_code == 404

    week = client.post(
        "/api/v1/checklists/weeks", json={"first_day": _d(95), "last_day": _d(95)}
    ).json()
    ad_hoc_response = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": category_id, "day_of_week": 1},
    )
    assert ad_hoc_response.status_code == 404

    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")


def test_monthly_analytics_splits_a_week_that_crosses_month_boundary(db_session):
    """Semana sintetica Jan29-Feb4/2015 (fuera de rango de cualquier otro
    test): cada dia debe caer en el mes calendario que le corresponde de
    verdad, no todo en el mes de first_day."""
    category_id = _make_category("Cross-month test")
    first_day = date(2015, 1, 29)
    daily_scores = [10, 5, 5, 5, 5, 0, 5]  # offsets 0..6 -> Jan29..Feb4

    week = ChecklistWeek(
        user_id=1,
        first_day=first_day,
        last_day=first_day + timedelta(days=6),
        closed=True,
        closed_date=None,
        score=sum(daily_scores),
    )
    db_session.add(week)
    db_session.flush()
    for offset, score in enumerate(daily_scores):
        actual_date = first_day + timedelta(days=offset)
        db_session.add(
            ChecklistWeekCategoryDayScore(
                cl_week_id=week.id,
                category_id=category_id,
                day_of_week=actual_date.isoweekday(),
                score=score,
                points_possible=score,
            )
        )
    db_session.commit()

    expected_jan = sum(
        score for offset, score in enumerate(daily_scores) if (first_day + timedelta(days=offset)).month == 1
    )
    expected_feb = sum(
        score for offset, score in enumerate(daily_scores) if (first_day + timedelta(days=offset)).month == 2
    )
    assert expected_jan + expected_feb == sum(daily_scores)

    body = client.get("/api/v1/checklists/analytics/monthly", params={"year": 2015}).json()
    index = next(i for i, c in enumerate(body["categories"]) if c["category_id"] == category_id)
    january = next(m for m in body["months"] if m["month"] == 1)
    february = next(m for m in body["months"] if m["month"] == 2)
    assert january["scores"][index] == expected_jan
    assert february["scores"][index] == expected_feb


def test_weekly_analytics_groups_low_scoring_categories_into_others(db_session):
    category_ids = [_make_category(f"Bucket {i}") for i in range(9)]
    scores = [100, 90, 80, 70, 60, 50, 40, 30, 20]  # las 2 ultimas van a "Others"

    week = ChecklistWeek(
        user_id=1,
        first_day=date(2014, 1, 1),
        last_day=date(2014, 1, 7),
        closed=True,
        closed_date=None,
        score=sum(scores),
    )
    db_session.add(week)
    db_session.flush()
    for category_id, score in zip(category_ids, scores):
        db_session.add(
            ChecklistWeekCategoryDayScore(
                cl_week_id=week.id,
                category_id=category_id,
                day_of_week=1,
                score=score,
                points_possible=score,
            )
        )
    db_session.commit()

    body = client.get("/api/v1/checklists/analytics/weekly", params={"year": 2014}).json()
    assert len(body["categories"]) == 8
    assert body["categories"][-1] == {"category_id": None, "name": "Others"}

    week_point = body["weeks"][0]
    assert week_point["scores"][-1] == 30 + 20
    assert sum(week_point["scores"]) == sum(scores)


def test_analytics_for_year_with_no_closed_weeks_is_empty():
    body = client.get("/api/v1/checklists/analytics/weekly", params={"year": 2010}).json()
    assert body == {"year": 2010, "categories": [], "weeks": []}


# --- Categorias deshabilitadas: visibilidad y reactivacion ---


def _disable_category(category_id: int) -> None:
    remaining = [c for c in client.get("/api/v1/checklists/categories").json() if c["id"] != category_id]
    client.put(
        "/api/v1/checklists/categories",
        json={"items": [{"id": c["id"], "name": c["name"]} for c in remaining]},
    )


def test_disabled_category_can_be_re_enabled():
    _make_category("Se queda habilitada")  # referencia para comparar prioridades
    category_id = _make_category("Re-enable me")
    _disable_category(category_id)
    assert category_id not in {c["id"] for c in client.get("/api/v1/checklists/categories").json()}

    response = client.post(f"/api/v1/checklists/categories/{category_id}/enable")
    assert response.status_code == 200
    assert response.json()["status"] == "ENABLED"

    listed = client.get("/api/v1/checklists/categories").json()
    assert category_id in {c["id"] for c in listed}
    # Vuelve al final: prioridad mayor a la de cualquier otra categoria habilitada.
    reenabled = next(c for c in listed if c["id"] == category_id)
    others_max_priority = max(c["priority"] for c in listed if c["id"] != category_id)
    assert reenabled["priority"] > others_max_priority


def test_enable_unknown_category_returns_404():
    response = client.post("/api/v1/checklists/categories/999999/enable")
    assert response.status_code == 404


def test_list_categories_include_disabled_puts_disabled_last():
    category_id = _make_category("Will list disabled")
    _disable_category(category_id)

    listed = client.get("/api/v1/checklists/categories", params={"include_disabled": True}).json()
    assert category_id in {c["id"] for c in listed}
    statuses = [c["status"] for c in listed]
    first_disabled_index = statuses.index("DISABLED")
    assert all(s == "ENABLED" for s in statuses[:first_disabled_index])
    assert all(s == "DISABLED" for s in statuses[first_disabled_index:])


def test_disabled_category_tasks_are_hidden_but_dont_block_close_and_still_score():
    category_id = _make_category("Hidden after disable")
    week = client.post(
        "/api/v1/checklists/weeks", json={"first_day": _d(96), "last_day": _d(96)}
    ).json()

    complete_task = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={
            "name": "Done before disable",
            "importance": "HIGH",
            "category_id": category_id,
            "day_of_week": 1,
        },
    ).json()
    pending_task = client.post(
        f"/api/v1/checklists/weeks/{week['id']}/tasks",
        json={
            "name": "Left pending",
            "importance": "STANDARD",
            "category_id": category_id,
            "day_of_week": 1,
        },
    ).json()

    # Resuelve todo lo demas que haya en la semana (tareas heredadas del
    # template acumulado por otros tests) para poder cerrarla mas adelante;
    # pending_task se deja PENDING a proposito.
    for task in client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json():
        if task["id"] == complete_task["id"]:
            client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "COMPLETE"})
        elif task["id"] != pending_task["id"]:
            client.patch(f"/api/v1/checklists/tasks/{task['id']}", json={"status": "FAILED"})

    _disable_category(category_id)

    visible = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    assert all(t["category_id"] != category_id for t in visible)
    assert all(t["status"] != "PENDING" for t in visible)

    closed = client.post(f"/api/v1/checklists/weeks/{week['id']}/close")
    assert closed.status_code == 200
    # Solo "Done before disable" (HIGH) suma: el pending invisible no bloquea
    # el cierre ni suma, pero tampoco impide que el resto de la semana cierre.
    assert closed.json()["score"] == 2
