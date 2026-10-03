"""Aislamiento entre usuarios.

A es el usuario quemado (id 1, el que usa el cliente por defecto); B es
`other_user`. En cada recurso, B crea algo y A intenta leerlo, editarlo y
borrarlo: siempre 404, nunca 403 (un 403 confirmaria que el id existe, y
permitiria enumerar los recursos de otros). Despues se verifica, como B, que
el recurso quedo intacto.

Hay dos capas y se prueban las dos:
- La API (service + repository filtrando por user_id): tests por recurso.
- La base (FK compuestas): al final, insertando directo con el ORM, para
  comprobar que Postgres/SQLite rechazan una referencia cruzada aunque el
  codigo tuviera un bug.

weights y meals, y la edicion/borrado de gastos, ya tienen sus tests de
aislamiento en su propio archivo; aca se cubre lo que faltaba.
"""

from datetime import date, timedelta

import pytest
from sqlalchemy.exc import IntegrityError

from app.db.models.checklist import ChecklistTask, ChecklistWeek, ChecklistWeekCategoryDayScore
from app.db.models.cld_task import CldTask
from app.db.models.cld_user_event import CldUserEvent
from app.db.models.finance import Category, IncomeSource, IncomeSubcategory, PaymentMethod, Tag
from app.repositories.sqlalchemy_category_repository import SqlAlchemyCategoryRepository
from app.repositories.sqlalchemy_cld_task_repository import SqlAlchemyCldTaskRepository
from app.repositories.sqlalchemy_task_repository import SqlAlchemyTaskRepository
from app.repositories.sqlalchemy_template_task_repository import SqlAlchemyTemplateTaskRepository
from app.repositories.sqlalchemy_week_category_day_score_repository import (
    SqlAlchemyWeekCategoryDayScoreRepository,
)
from app.repositories.sqlalchemy_week_repository import SqlAlchemyWeekRepository
from tests.conftest import acting_as, client

API = "/api/v1"
TODAY = date.today()


def _iso(offset: int) -> str:
    return (TODAY + timedelta(days=offset)).isoformat()


# --- Helpers: crean como el usuario que este activo en ese momento ---


def _make_category(name: str) -> int:
    current = client.get(f"{API}/checklists/categories").json()
    items = [{"id": c["id"], "name": c["name"]} for c in current] + [{"name": name}]
    updated = client.put(f"{API}/checklists/categories", json={"items": items}).json()
    return next(c["id"] for c in updated if c["name"] == name)


def _open_week() -> int:
    response = client.post(
        f"{API}/checklists/weeks", json={"first_day": _iso(0), "last_day": _iso(6)}
    )
    assert response.status_code == 201
    return response.json()["id"]


def _task_payload(category_id: int, name: str = "Tarea") -> dict:
    return {"name": name, "importance": "HIGH", "category_id": category_id, "day_of_week": 1}


def _create_week_task(week_id: int, category_id: int, name: str = "Tarea") -> int:
    response = client.post(
        f"{API}/checklists/weeks/{week_id}/tasks", json=_task_payload(category_id, name)
    )
    assert response.status_code == 201
    return response.json()["id"]


def _cld_payload(category_id: int, name: str = "Cita") -> dict:
    return {
        "name": name,
        "importance": "STANDARD",
        "category_id": category_id,
        "notify": False,
        "scheduled_date": f"{_iso(2)}T10:00:00",
        "duration_minutes": 30,
    }


def _create_cld_task(category_id: int, name: str = "Cita") -> int:
    response = client.post(f"{API}/calendar-tasks", json=_cld_payload(category_id, name))
    assert response.status_code == 201
    return response.json()["id"]


# --- Checklists: categorias ---


def test_another_users_category_is_invisible_and_untouchable(other_user):
    with acting_as(other_user):
        category_id = _make_category("De B")

    assert (
        client.get(f"{API}/checklists/categories", params={"include_disabled": True}).json() == []
    )
    assert client.post(f"{API}/checklists/categories/{category_id}/enable").status_code == 404
    # El guardado en bloque con un id ajeno: no puede renombrarla ni adueñarse de ella.
    renamed = client.put(
        f"{API}/checklists/categories", json={"items": [{"id": category_id, "name": "Robada"}]}
    )
    assert renamed.status_code == 404

    with acting_as(other_user):
        [category] = client.get(f"{API}/checklists/categories").json()
    assert category == {"id": category_id, "name": "De B", "priority": 1, "status": "ENABLED"}


# --- Checklists: template ---


def test_another_users_template_task_returns_404(other_user):
    with acting_as(other_user):
        category_id = _make_category("De B")
        task_id = client.post(
            f"{API}/checklists/template/tasks",
            json={"name": "Ajena", "importance": "HIGH", "category_id": category_id, "days": [1]},
        ).json()["id"]
    own_category_id = _make_category("Mia")
    url = f"{API}/checklists/template/tasks/{task_id}"

    assert client.get(f"{API}/checklists/template/tasks").json() == []
    update = {"name": "Pisada", "importance": "STANDARD", "category_id": own_category_id}
    assert client.put(url, params={"day": 1}, json=update).status_code == 404
    assert client.delete(url, params={"day": 1}).status_code == 404

    with acting_as(other_user):
        [task] = client.get(f"{API}/checklists/template/tasks").json()
    assert (task["name"], task["days"], task["category_id"]) == ("Ajena", [1], category_id)


def test_template_task_cannot_use_another_users_category(other_user):
    with acting_as(other_user):
        foreign_category_id = _make_category("De B")

    response = client.post(
        f"{API}/checklists/template/tasks",
        json={"name": "X", "importance": "HIGH", "category_id": foreign_category_id, "days": [1]},
    )

    assert response.status_code == 404
    assert client.get(f"{API}/checklists/template/tasks").json() == []


# --- Checklists: semanas ---


def test_another_users_week_returns_404(other_user):
    with acting_as(other_user):
        category_id = _make_category("De B")
        week_id = _open_week()
        _create_week_task(week_id, category_id, "De B")
    own_category_id = _make_category("Mia")

    assert client.get(f"{API}/checklists/weeks/current").json() is None
    assert client.get(f"{API}/checklists/weeks/{week_id}/tasks").status_code == 404
    created = client.post(
        f"{API}/checklists/weeks/{week_id}/tasks", json=_task_payload(own_category_id)
    )
    assert created.status_code == 404
    assert client.post(f"{API}/checklists/weeks/{week_id}/close").status_code == 404

    with acting_as(other_user):
        current = client.get(f"{API}/checklists/weeks/current").json()
        tasks = client.get(f"{API}/checklists/weeks/{week_id}/tasks").json()
    assert current["id"] == week_id and current["closed"] is False
    assert [t["name"] for t in tasks] == ["De B"]


def test_another_users_open_week_does_not_block_own_week(other_user):
    """La unicidad de "una semana abierta" es por usuario."""
    with acting_as(other_user):
        _open_week()

    assert client.get(f"{API}/checklists/weeks/next-range").status_code == 200
    _open_week()


# --- Checklists: tareas de una semana ---


def test_another_users_week_task_returns_404(other_user):
    with acting_as(other_user):
        category_id = _make_category("De B")
        task_id = _create_week_task(_open_week(), category_id, "De B")
    own_category_id = _make_category("Mia")
    url = f"{API}/checklists/tasks/{task_id}"

    assert client.patch(url, json={"status": "COMPLETE"}).status_code == 404
    update = {"name": "Pisada", "importance": "STANDARD", "category_id": own_category_id}
    assert client.put(url, json=update).status_code == 404
    assert client.delete(url).status_code == 404

    with acting_as(other_user):
        week_id = client.get(f"{API}/checklists/weeks/current").json()["id"]
        [task] = client.get(f"{API}/checklists/weeks/{week_id}/tasks").json()
    assert (task["name"], task["status"]) == ("De B", "PENDING")


def test_week_task_cannot_use_another_users_category(other_user):
    with acting_as(other_user):
        foreign_category_id = _make_category("De B")
    week_id = _open_week()
    own_task_id = _create_week_task(week_id, _make_category("Mia"))

    created = client.post(
        f"{API}/checklists/weeks/{week_id}/tasks", json=_task_payload(foreign_category_id)
    )
    updated = client.put(
        f"{API}/checklists/tasks/{own_task_id}",
        json={"name": "X", "importance": "HIGH", "category_id": foreign_category_id},
    )

    assert created.status_code == 404
    assert updated.status_code == 404


# --- Checklists: analytics ---


def _closed_week_with_score(db_session, user_id: int, category_id: int, year: int) -> None:
    week = ChecklistWeek(
        user_id=user_id,
        first_day=date(year, 3, 2),
        last_day=date(year, 3, 8),
        closed=True,
        score=5,
    )
    db_session.add(week)
    db_session.flush()
    db_session.add(
        ChecklistWeekCategoryDayScore(
            user_id=user_id,
            cl_week_id=week.id,
            category_id=category_id,
            day_of_week=1,
            score=5,
            points_possible=5,
        )
    )
    db_session.commit()


@pytest.mark.parametrize("view", ["weekly", "monthly"])
def test_analytics_ignore_another_users_weeks(db_session, other_user, view):
    with acting_as(other_user):
        category_id = _make_category("De B")
    _closed_week_with_score(db_session, other_user, category_id, year=2015)
    url = f"{API}/checklists/analytics/{view}"

    mine = client.get(url, params={"year": 2015}).json()
    with acting_as(other_user):
        theirs = client.get(url, params={"year": 2015}).json()

    # Sin el control de B, un resultado vacio de A no probaria nada.
    assert [c["name"] for c in theirs["categories"]] == ["De B"]
    assert mine["categories"] == []
    assert all(sum(point["scores"]) == 0 for point in mine.get("weeks", mine.get("months", [])))


# --- Calendario: tareas ---


def test_another_users_calendar_task_returns_404(other_user):
    with acting_as(other_user):
        category_id = _make_category("De B")
        task_id = _create_cld_task(category_id, "De B")
    own_category_id = _make_category("Mia")
    url = f"{API}/calendar-tasks/{task_id}"

    assert client.get(f"{API}/calendar-tasks", params={"date": _iso(2)}).json() == []
    update = {**_cld_payload(own_category_id, "Pisada"), "notify": True}
    assert client.put(url, json=update).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.post(f"{url}/checklist", params={"occurrence_date": _iso(2)}).status_code == 404

    with acting_as(other_user):
        [occurrence] = client.get(f"{API}/calendar-tasks", params={"date": _iso(2)}).json()
    assert (occurrence["name"], occurrence["notify"]) == ("De B", False)


def test_calendar_task_cannot_use_another_users_category(other_user):
    with acting_as(other_user):
        foreign_category_id = _make_category("De B")
    own_task_id = _create_cld_task(_make_category("Mia"))

    created = client.post(f"{API}/calendar-tasks", json=_cld_payload(foreign_category_id))
    updated = client.put(
        f"{API}/calendar-tasks/{own_task_id}", json=_cld_payload(foreign_category_id)
    )

    assert created.status_code == 404
    assert updated.status_code == 404


# --- Calendario: eventos personales (sin CRUD todavia, solo lectura) ---


@pytest.mark.parametrize("path", ["", "/ranges"])
def test_another_users_calendar_events_are_not_listed(db_session, other_user, path):
    with acting_as(other_user):
        category_id = _make_category("De B")
    db_session.add(
        CldUserEvent(
            user_id=other_user,
            category_id=category_id,
            code="TRAVEL",
            first_day=TODAY,
            last_day=TODAY + timedelta(days=2),
            name="Viaje de B",
        )
    )
    db_session.commit()
    params = {"first_day": _iso(0), "last_day": _iso(6)}

    mine = client.get(f"{API}/calendar-events{path}", params=params).json()
    with acting_as(other_user):
        theirs = client.get(f"{API}/calendar-events{path}", params=params).json()

    assert "Viaje de B" in str(theirs)
    assert "Viaje de B" not in str(mine)


# --- Finanzas: la validacion de referencias vive en el service ---


def test_expense_cannot_use_another_users_tag(db_session, other_user):
    category = Category(name="Groceries", icon_key="shopping-cart", color_key="lime")
    payment_method = PaymentMethod(name="Cash", icon_key="banknote", color_key="green")
    foreign_tag = Tag(user_id=other_user, name="DE B", color_key="emerald")
    db_session.add_all([category, payment_method, foreign_tag])
    db_session.commit()

    response = client.post(
        f"{API}/expenses/",
        json={
            "name": "Mercado",
            "amount": 1000,
            "recorded_on": "2026-09-26",
            "payment_method_id": payment_method.id,
            "category_id": category.id,
            "tag_ids": [foreign_tag.id],
        },
    )

    assert response.status_code == 404
    assert client.get(f"{API}/expenses/").json()["total"] == 0


def _seed_income_catalog(db_session, user_id: int) -> dict[str, int]:
    direct = IncomeSource(user_id=user_id, type="DIRECT", name="Salario")
    interest = IncomeSource(user_id=user_id, type="INTEREST", name="Tyba")
    tag = Tag(user_id=user_id, name="RECURRING", color_key="violet")
    db_session.add_all([direct, interest, tag])
    db_session.flush()
    base = IncomeSubcategory(user_id=user_id, source_id=direct.id, type="DIRECT", name="BASE")
    earned = IncomeSubcategory(
        user_id=user_id, source_id=interest.id, type="INTEREST", name="RENDIMIENTOS"
    )
    db_session.add_all([base, earned])
    db_session.commit()
    return {
        "direct": direct.id,
        "interest": interest.id,
        "tag": tag.id,
        "base": base.id,
        "earned": earned.id,
    }


def _direct_payload(ids: dict[str, int], **overrides) -> dict:
    return {
        "amount": 1000,
        "recorded_on": "2026-09-15",
        "source_id": ids["direct"],
        "subcategory_id": ids["base"],
        "tag_ids": [ids["tag"]],
        **overrides,
    }


def _interest_payload(ids: dict[str, int], **overrides) -> dict:
    return {
        "amount": 500,
        "recorded_on": "2026-08-20",
        "source_id": ids["interest"],
        "subcategory_id": ids["earned"],
        **overrides,
    }


@pytest.mark.parametrize(
    ("kind", "payload"), [("direct", _direct_payload), ("interest", _interest_payload)]
)
def test_another_users_income_returns_404(db_session, other_user, kind, payload):
    foreign_ids = _seed_income_catalog(db_session, other_user)
    own_ids = _seed_income_catalog(db_session, 1)
    with acting_as(other_user):
        created = client.post(f"{API}/incomes/{kind}", json=payload(foreign_ids))
        assert created.status_code == 201
        record_id = created.json()["id"]
    url = f"{API}/incomes/{kind}/{record_id}"

    assert client.get(f"{API}/incomes/{kind}").json()["total"] == 0
    assert client.put(url, json=payload(own_ids, amount=1)).status_code == 404
    assert client.delete(url).status_code == 404

    with acting_as(other_user):
        [record] = client.get(f"{API}/incomes/{kind}").json()["items"]
    assert record["amount"] == payload(foreign_ids)["amount"]


@pytest.mark.parametrize(
    "overrides",
    [
        lambda foreign: {"subcategory_id": foreign["base"]},
        lambda foreign: {"tag_ids": [foreign["tag"]]},
    ],
    ids=["subcategory", "tag"],
)
def test_income_cannot_use_another_users_catalog(db_session, other_user, overrides):
    foreign_ids = _seed_income_catalog(db_session, other_user)
    own_ids = _seed_income_catalog(db_session, 1)

    response = client.post(
        f"{API}/incomes/direct", json=_direct_payload(own_ids, **overrides(foreign_ids))
    )

    assert response.status_code == 404
    assert client.get(f"{API}/incomes/direct").json()["total"] == 0


# --- La base: FK compuestas, sin pasar por la API ---


def _week_task(**fields) -> ChecklistTask:
    return ChecklistTask(name="X", day_of_week="1", importance="HIGH", status="PENDING", **fields)


def _cld_task(**fields) -> CldTask:
    return CldTask(name="X", importance="HIGH", scheduled_date=None, **fields)


def _score(**fields) -> ChecklistWeekCategoryDayScore:
    return ChecklistWeekCategoryDayScore(day_of_week=1, score=1, points_possible=1, **fields)


@pytest.mark.parametrize(
    "build",
    [
        # Tarea de A, en la semana de A, con la categoria de B.
        lambda a_week, a_cat, b_cat: _week_task(user_id=1, cl_week_id=a_week, category_id=b_cat),
        # Tarea que dice ser de B pero cuelga de la semana de A.
        lambda a_week, a_cat, b_cat: _week_task(user_id=2, cl_week_id=a_week, category_id=b_cat),
        lambda a_week, a_cat, b_cat: _score(user_id=1, cl_week_id=a_week, category_id=b_cat),
        lambda a_week, a_cat, b_cat: _score(user_id=2, cl_week_id=a_week, category_id=b_cat),
        lambda a_week, a_cat, b_cat: _cld_task(user_id=1, category_id=b_cat),
    ],
    ids=[
        "week_task_foreign_category",
        "week_task_foreign_week",
        "score_foreign_category",
        "score_foreign_week",
        "cld_task_foreign_category",
    ],
)
def test_database_rejects_cross_user_references(db_session, other_user, build):
    with acting_as(other_user):
        b_cat = _make_category("De B")
    a_cat = _make_category("Mia")
    a_week = _open_week()

    db_session.add(build(a_week, a_cat, b_cat))
    with pytest.raises(IntegrityError):
        db_session.flush()
    db_session.rollback()


def test_database_accepts_same_user_references(db_session):
    """Control del test de arriba: con todo del mismo usuario, la fila entra."""
    a_cat = _make_category("Mia")
    a_week = _open_week()

    db_session.add(_week_task(user_id=1, cl_week_id=a_week, category_id=a_cat))
    db_session.add(_score(user_id=1, cl_week_id=a_week, category_id=a_cat))
    db_session.add(_cld_task(user_id=1, category_id=a_cat))
    db_session.flush()


# --- Repositories: cada metodo filtra por user_id por su cuenta ---
#
# Los tests de API de arriba no alcanzan para esto: varios services vuelven a
# buscar el padre filtrando por usuario (ej. la semana de una tarea), asi que
# un repository que olvidara su filtro seguiria respondiendo 404. Aca se
# llama a cada metodo con un id de B y el user_id de A.


@pytest.fixture
def foreign_rows(db_session, other_user) -> dict[str, int]:
    """Una fila de B en cada tabla de checklist/calendario."""
    with acting_as(other_user):
        category_id = _make_category("De B")
        template_id = client.post(
            f"{API}/checklists/template/tasks",
            json={"name": "T", "importance": "HIGH", "category_id": category_id, "days": [1]},
        ).json()["id"]
        week_id = _open_week()
        task_id = _create_week_task(week_id, category_id)
        cld_task_id = _create_cld_task(category_id)
    db_session.add(_score(user_id=other_user, cl_week_id=week_id, category_id=category_id))
    db_session.commit()
    return {
        "category": category_id,
        "template": template_id,
        "week": week_id,
        "task": task_id,
        "cld_task": cld_task_id,
    }


def test_repositories_do_not_return_another_users_rows(db_session, foreign_rows):
    a, b, ids = 1, 2, foreign_rows
    weeks = SqlAlchemyWeekRepository(db_session)
    tasks = SqlAlchemyTaskRepository(db_session)
    scores = SqlAlchemyWeekCategoryDayScoreRepository(db_session)
    categories = SqlAlchemyCategoryRepository(db_session)
    templates = SqlAlchemyTemplateTaskRepository(db_session)
    cld_tasks = SqlAlchemyCldTaskRepository(db_session)

    # Control: como B, cada consulta si encuentra su fila.
    assert weeks.get(ids["week"], user_id=b) is not None
    assert tasks.get(ids["task"], user_id=b) is not None
    assert tasks.list_by_week(ids["week"], user_id=b)
    assert tasks.list_visible_by_week(ids["week"], user_id=b)
    assert scores.list_by_week_ids([ids["week"]], user_id=b)
    assert categories.get(ids["category"], user_id=b) is not None
    assert categories.has_template_tasks(ids["category"], user_id=b)
    assert templates.get(ids["template"], user_id=b) is not None
    assert cld_tasks.get(ids["cld_task"], user_id=b) is not None

    # Como A, ninguna.
    assert weeks.get(ids["week"], user_id=a) is None
    assert tasks.get(ids["task"], user_id=a) is None
    assert tasks.list_by_week(ids["week"], user_id=a) == []
    assert tasks.list_visible_by_week(ids["week"], user_id=a) == []
    assert scores.list_by_week_ids([ids["week"]], user_id=a) == []
    assert categories.get(ids["category"], user_id=a) is None
    assert not categories.has_template_tasks(ids["category"], user_id=a)
    assert templates.get(ids["template"], user_id=a) is None
    assert cld_tasks.get(ids["cld_task"], user_id=a) is None
