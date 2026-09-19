"""Pruebas de categorias y tareas de template de checklist.

Usa SQLite en memoria (igual que test_weights.py) para no depender de Postgres.
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
from app.db.models import checklist as checklist_model  # noqa: F401
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


def test_create_week_requires_seven_day_range():
    response = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": "2026-09-19", "last_day": "2026-09-24"},
    )
    assert response.status_code == 422


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
        json={"first_day": "2026-09-19", "last_day": "2026-09-25"},
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
    response = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": "2026-09-26", "last_day": "2026-10-02"},
    )
    assert response.status_code == 409


def test_update_status_and_close_week_computes_score():
    current = client.get("/api/v1/checklists/weeks/current").json()
    week_id = current["id"]
    tasks = client.get(f"/api/v1/checklists/weeks/{week_id}/tasks").json()

    gym_day1 = next(t for t in tasks if t["name"] == "Gym" and t["day_of_week"] == 1)
    water_day1 = next(t for t in tasks if t["name"] == "Water" and t["day_of_week"] == 1)
    # el Gym del dia 3 se deja en PENDING a proposito

    completed = client.patch(
        f"/api/v1/checklists/tasks/{gym_day1['id']}", json={"status": "COMPLETE"}
    )
    assert completed.status_code == 200
    assert completed.json()["status"] == "COMPLETE"

    failed = client.patch(
        f"/api/v1/checklists/tasks/{water_day1['id']}", json={"status": "FAILED"}
    )
    assert failed.json()["status"] == "FAILED"

    closed = client.post(f"/api/v1/checklists/weeks/{week_id}/close")
    assert closed.status_code == 200
    closed_body = closed.json()
    assert closed_body["closed"] is True
    assert closed_body["closed_date"] is not None
    # Solo el Gym HIGH completado suma: 2 puntos. Water (FAILED) y el Gym
    # del dia 3 (PENDING) no aportan.
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
        json={"first_day": "2026-10-03", "last_day": "2026-10-09"},
    ).json()
    client.post(f"/api/v1/checklists/weeks/{week['id']}/close")

    tasks = client.get(f"/api/v1/checklists/weeks/{week['id']}/tasks").json()
    task_id = tasks[0]["id"]

    response = client.patch(
        f"/api/v1/checklists/tasks/{task_id}", json={"status": "COMPLETE"}
    )
    assert response.status_code == 409


def test_close_week_twice_returns_409():
    week = client.post(
        "/api/v1/checklists/weeks",
        json={"first_day": "2026-10-10", "last_day": "2026-10-16"},
    ).json()
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
