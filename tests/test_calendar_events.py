"""Pruebas de eventos de calendario: festivos/eventos generales (cld_events)
y eventos personales (cld_user_events), vistos como marcadores de
inicio/fin/dia-unico dentro de un rango (vista semanal).

Usa SQLite en memoria (igual que test_checklists.py) para no depender de Postgres.
"""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base_class import Base
from app.db.models.cld_event import CldEvent
from app.db.models.cld_user_event import CldUserEvent
from app.db.seed import ensure_default_user
from app.db.session import get_db
from app.main import app

# Importar los modelos para que sus tablas queden registradas en Base.metadata
from app.db.models import checklist as checklist_model  # noqa: F401
from app.db.models import cld_task as cld_task_model  # noqa: F401
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

TODAY = date.today()


def _d(offset: int) -> date:
    return TODAY + timedelta(days=offset)


def _make_category(name: str) -> int:
    current = client.get("/api/v1/checklists/categories").json()
    items = [{"id": c["id"], "name": c["name"]} for c in current] + [{"name": name}]
    updated = client.put("/api/v1/checklists/categories", json={"items": items}).json()
    return next(c["id"] for c in updated if c["name"] == name)


def _insert(model, **kwargs) -> None:
    """Inserta directo (no hay endpoint de escritura para cld_events /
    cld_user_events todavia). Usa la sesion que este activa en
    app.dependency_overrides[get_db] en este momento, no el engine propio de
    este archivo: varios test_*.py de este proyecto comparten el mismo
    dependency_overrides global, y el ultimo modulo importado por pytest es
    el que termina quedando activo para todos. Escribir siempre contra la
    sesion realmente activa evita que este insert quede en un engine que
    el `client` de este archivo despues no lee."""
    gen = app.dependency_overrides[get_db]()
    db = next(gen)
    try:
        db.add(model(**kwargs))
        db.commit()
    finally:
        gen.close()


def test_single_day_event_gives_one_marker():
    _insert(CldEvent, code="HOLIDAY", first_day=_d(500), last_day=_d(500), name="Test holiday", detail=None)

    response = client.get(f"/api/v1/calendar-events?first_day={_d(497)}&last_day={_d(503)}")
    assert response.status_code == 200
    matching = [m for m in response.json() if m["name"] == "Test holiday"]
    assert len(matching) == 1
    assert matching[0]["marker_type"] == "single"
    assert matching[0]["marker_date"] == _d(500).isoformat()
    assert matching[0]["source"] == "event"
    assert matching[0]["code"] == "HOLIDAY"


def test_holiday_outside_range_is_not_returned():
    _insert(CldEvent, code="HOLIDAY", first_day=_d(510), last_day=_d(510), name="Far holiday", detail=None)

    response = client.get(f"/api/v1/calendar-events?first_day={_d(497)}&last_day={_d(503)}").json()
    assert all(m["name"] != "Far holiday" for m in response)


def test_multi_day_user_event_gives_start_and_end_markers_when_both_in_range():
    category_id = _make_category("Events test category")
    _insert(
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


def test_multi_day_event_gives_only_the_boundary_that_falls_in_the_requested_range():
    category_id = _make_category("Events partial overlap")
    _insert(
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
    start_week = client.get(f"/api/v1/calendar-events?first_day={_d(529)}&last_day={_d(535)}").json()
    start_matching = [m for m in start_week if m["name"] == "Long trip"]
    assert len(start_matching) == 1
    assert start_matching[0]["marker_type"] == "start"

    # Semana que solo cubre el final del viaje
    end_week = client.get(f"/api/v1/calendar-events?first_day={_d(538)}&last_day={_d(544)}").json()
    end_matching = [m for m in end_week if m["name"] == "Long trip"]
    assert len(end_matching) == 1
    assert end_matching[0]["marker_type"] == "end"

    # Semana intermedia, sin ninguno de los dos bordes: no aparece
    middle_week = client.get(f"/api/v1/calendar-events?first_day={_d(536)}&last_day={_d(536)}").json()
    assert all(m["name"] != "Long trip" for m in middle_week)


def test_ranges_endpoint_returns_the_full_span_not_just_boundaries():
    _insert(CldEvent, code="HOLIDAY", first_day=_d(550), last_day=_d(550), name="Range test holiday", detail=None)
    category_id = _make_category("Ranges test category")
    _insert(
        CldUserEvent,
        user_id=1,
        category_id=category_id,
        code="TRAVEL",
        first_day=_d(560),
        last_day=_d(562),
        name="Conference",
        detail=None,
    )

    response = client.get(f"/api/v1/calendar-events/ranges?first_day={_d(548)}&last_day={_d(565)}").json()

    holiday = next(r for r in response if r["name"] == "Range test holiday")
    assert holiday["first_day"] == holiday["last_day"] == _d(550).isoformat()
    assert holiday["source"] == "event"
    assert holiday["code"] == "HOLIDAY"

    conference = next(r for r in response if r["name"] == "Conference")
    assert conference["first_day"] == _d(560).isoformat()
    assert conference["last_day"] == _d(562).isoformat()
    assert conference["source"] == "user_event"
    assert conference["code"] == "TRAVEL"


def test_ranges_endpoint_excludes_events_entirely_outside_the_range():
    _insert(CldEvent, code="HOLIDAY", first_day=_d(570), last_day=_d(570), name="Out of range holiday", detail=None)

    response = client.get(f"/api/v1/calendar-events/ranges?first_day={_d(548)}&last_day={_d(565)}").json()
    assert all(r["name"] != "Out of range holiday" for r in response)
