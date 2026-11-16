"""Dashboard ("Quick access"): vista Today, pulso semanal e interpretacion con IA.

"Hoy" se fija con `get_clock`: miercoles 2026-11-18 en Bogota. La semana
sabado-viernes en curso va del 14 al 20 de noviembre (dia 5 de 7).
"""

import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from app.api.deps import get_clock, get_current_permissions, get_text_generator
from app.db.models.ai_usage import AiUsageEvent
from app.db.models.checklist import (
    ChecklistCategory,
    ChecklistTask,
    ChecklistWeek,
    ChecklistWeekCategoryDayScore,
)
from app.db.models.cld_event import CldEvent
from app.db.models.cld_user_event import CldUserEvent
from app.db.models.english import EngPractice
from app.db.models.finance import Category, Expense, PaymentMethod
from app.db.models.weight import WeightRecord
from app.integrations.openai_client import GeneratedText, TextGenerationError
from app.main import app
from app.services.permissions import ALL_PERMISSIONS, Permission
from tests.conftest import client
from tests.english_fixtures import practice_payload, seed_bank
from tests.test_incomes import _direct_payload, _seed

API = "/api/v1/dashboard"
NOW = datetime(2026, 11, 18, 15, 0, tzinfo=UTC)  # 10:00 en Bogota


@pytest.fixture(autouse=True)
def fixed_clock():
    app.dependency_overrides[get_clock] = lambda: lambda: NOW


def _permissions(*permissions: Permission) -> None:
    app.dependency_overrides[get_current_permissions] = lambda: frozenset(permissions)


# --- Today ---


def _seed_events(db_session) -> None:
    category = ChecklistCategory(user_id=1, name="Personal", priority=1)
    db_session.add(category)
    db_session.flush()
    db_session.add_all(
        [
            CldEvent(
                code="HOLIDAY",
                first_day=date(2026, 11, 16),
                last_day=date(2026, 11, 18),
                name="Puente",
            ),
            CldEvent(
                code="HOLIDAY",
                first_day=date(2026, 11, 25),
                last_day=date(2026, 11, 25),
                name="Otro dia",
            ),
            CldUserEvent(
                user_id=1,
                category_id=category.id,
                code="TRIP",
                first_day=date(2026, 11, 18),
                last_day=date(2026, 11, 18),
                name="Viaje",
            ),
        ]
    )
    db_session.commit()


def test_today_shows_global_events_to_everyone(db_session):
    _seed_events(db_session)
    _permissions()

    body = client.get(f"{API}/today").json()

    assert body["date"] == "2026-11-18"
    assert [e["name"] for e in body["events"]] == ["Puente"]
    assert body["weight"] is None
    assert body["english"] is None


def test_today_adds_personal_events_with_planning(db_session):
    _seed_events(db_session)

    body = client.get(f"{API}/today").json()

    assert sorted(e["name"] for e in body["events"]) == ["Puente", "Viaje"]


def test_today_reports_the_last_weight_and_practice(db_session):
    db_session.add_all(
        [
            WeightRecord(user_id=1, weight_kg=Decimal("72.5"), recorded_on=date(2026, 11, 10)),
            WeightRecord(user_id=1, weight_kg=Decimal("73.0"), recorded_on=date(2026, 11, 3)),
        ]
    )
    db_session.commit()

    body = client.get(f"{API}/today").json()

    assert body["weight"] == {"last_recorded_on": "2026-11-10", "last_kg": 72.5}
    assert body["english"] == {"last_practice_at": None}


# --- Pulso: semana ---


def test_pulse_defaults_to_the_week_in_progress():
    week = client.get(f"{API}/pulse").json()["week"]

    assert week == {
        "first_day": "2026-11-14",
        "last_day": "2026-11-20",
        "in_progress": True,
        "elapsed_days": 5,
        "total_days": 7,
    }


def test_pulse_accepts_any_day_of_a_past_week():
    week = client.get(f"{API}/pulse?week_start=2026-11-11").json()["week"]

    assert week["first_day"] == "2026-11-07"
    assert week["in_progress"] is False
    assert week["elapsed_days"] == 7


def test_pulse_rejects_a_future_week():
    assert client.get(f"{API}/pulse?week_start=2026-11-21").status_code == 422


def test_pulse_only_includes_the_granted_domains():
    _permissions(Permission.WEIGHT)

    body = client.get(f"{API}/pulse").json()

    assert body["weight"] is not None
    assert body["planning"] is None
    assert body["finances"] is None
    assert body["english"] is None


# --- Pulso: dominios ---


def test_pulse_planning_mixes_closed_scores_and_the_open_week(db_session):
    category = ChecklistCategory(user_id=1, name="Health", priority=1)
    previous = ChecklistWeek(
        user_id=1, first_day=date(2026, 11, 7), last_day=date(2026, 11, 13), closed=True, score=3
    )
    current = ChecklistWeek(user_id=1, first_day=date(2026, 11, 14), last_day=date(2026, 11, 20))
    db_session.add_all([category, previous, current])
    db_session.flush()
    db_session.add_all(
        [
            # Semana anterior (cerrada): 3 de 4 puntos el sabado 7 (ISO 6).
            ChecklistWeekCategoryDayScore(
                user_id=1,
                cl_week_id=previous.id,
                category_id=category.id,
                day_of_week=6,
                score=3,
                points_possible=4,
            ),
            # Semana en curso (abierta): 2 de 3 puntos, en vivo desde las tareas.
            ChecklistTask(
                user_id=1,
                cl_week_id=current.id,
                name="Gym",
                day_of_week="1",
                importance="HIGH",
                category_id=category.id,
                status="COMPLETE",
            ),
            ChecklistTask(
                user_id=1,
                cl_week_id=current.id,
                name="Read",
                day_of_week="5",
                importance="STANDARD",
                category_id=category.id,
                status="PENDING",
            ),
        ]
    )
    db_session.commit()

    score = client.get(f"{API}/pulse").json()["planning"]["score_pct"]

    # Las 3 semanas sin checklist no cuentan en el promedio (no son 0%).
    assert score == {"current": 66.7, "previous": 75.0, "average": 75.0}


def _expense(category_id: int, method_id: int, amount: int, day: date) -> Expense:
    return Expense(
        user_id=1,
        name="x",
        amount=Decimal(amount),
        recorded_on=day,
        category_id=category_id,
        payment_method_id=method_id,
    )


def test_pulse_finances_compares_spending_and_finds_the_rising_category(db_session):
    food = Category(user_id=1, name="Food", icon_key="apple", color_key="lime")
    fun = Category(user_id=1, name="Fun", icon_key="music", color_key="pink")
    cash = PaymentMethod(user_id=1, name="Cash", icon_key="banknote", color_key="green")
    db_session.add_all([food, fun, cash])
    db_session.flush()
    db_session.add_all(
        [
            _expense(food.id, cash.id, 100, date(2026, 11, 15)),  # semana en curso
            _expense(fun.id, cash.id, 300, date(2026, 11, 16)),
            _expense(food.id, cash.id, 200, date(2026, 11, 8)),  # anterior
            _expense(fun.id, cash.id, 40, date(2026, 10, 20)),  # 4 semanas atras
        ]
    )
    db_session.commit()
    ids = _seed(db_session)
    payload = _direct_payload(ids, amount=1000, recorded_on="2026-11-01", tag_ids=[])
    assert client.post("/api/v1/incomes/direct", json=payload).status_code == 201

    finances = client.get(f"{API}/pulse").json()["finances"]

    # Semanas sin gasto cuentan como 0: promedio (200 + 0 + 0 + 40) / 4.
    assert finances["spent"] == {"current": 400.0, "previous": 200.0, "average": 60.0}
    assert finances["top_deviation"] == {"label": "Fun", "current": 300.0, "average": 10.0}
    # Mes en curso hasta hoy: 1000 de ingreso, 600 de gasto (100 + 300 + 200).
    assert finances["month_first_day"] == "2026-11-01"
    assert finances["month_last_day"] == "2026-11-18"
    assert finances["savings_rate_pct"] == 40.0


def test_pulse_finances_without_income_has_no_savings_rate():
    finances = client.get(f"{API}/pulse").json()["finances"]

    assert finances["savings_rate_pct"] is None
    assert finances["top_deviation"] is None


def test_pulse_weight_averages_each_week(db_session):
    db_session.add_all(
        [
            WeightRecord(user_id=1, weight_kg=Decimal("72"), recorded_on=date(2026, 11, 15)),
            WeightRecord(user_id=1, weight_kg=Decimal("71"), recorded_on=date(2026, 11, 17)),
            WeightRecord(user_id=1, weight_kg=Decimal("73"), recorded_on=date(2026, 11, 10)),
        ]
    )
    db_session.commit()

    weight = client.get(f"{API}/pulse").json()["weight"]["average_kg"]

    assert weight == {"current": 71.5, "previous": 73.0, "average": 73.0}


def test_pulse_english_counts_sessions_in_the_user_timezone(db_session):
    seed_bank(db_session, level="A1")
    assert client.put("/api/v1/english/settings", json={"level": "A1"}).status_code == 200
    for _ in range(2):
        practice = client.get("/api/v1/english/practices/next").json()
        response = client.post("/api/v1/english/practices", json=practice_payload(practice))
        assert response.status_code == 201
    first, second = db_session.query(EngPractice).order_by(EngPractice.id).all()
    # Sabado 14 a las 02:00 UTC = viernes 13 a las 21:00 en Bogota: semana anterior.
    first.completed_at = datetime(2026, 11, 14, 2, 0, tzinfo=UTC)
    second.completed_at = datetime(2026, 11, 14, 6, 0, tzinfo=UTC)
    db_session.commit()

    sessions = client.get(f"{API}/pulse").json()["english"]["sessions"]

    assert sessions == {"current": 1.0, "previous": 1.0, "average": 0.25}


# --- Interpretacion con IA ---


class FakeGenerator:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict] = []

    def generate(self, **kwargs) -> GeneratedText:
        self.calls.append(kwargs)
        if self.fail:
            raise TextGenerationError("RateLimitError")
        return GeneratedText(
            text="  - Bien  ", model="gpt-6-luna", input_tokens=50, output_tokens=10
        )


def test_interpretation_sends_the_server_side_pulse_and_records_usage(db_session):
    fake = FakeGenerator()
    app.dependency_overrides[get_text_generator] = lambda: fake
    _permissions(Permission.AI, Permission.WEIGHT)

    response = client.post(f"{API}/pulse/interpretation", json={})

    assert response.status_code == 200
    assert response.json() == {"text": "- Bien", "model": "gpt-6-luna"}
    sent = json.loads(fake.calls[0]["prompt"])
    assert sent["week"]["first_day"] == "2026-11-14"
    assert sent["weight"] is not None
    assert sent["finances"] is None  # sin permiso, no llega al LLM
    usage = db_session.query(AiUsageEvent).one()
    assert usage.feature == "dashboard.pulse"


def test_interpretation_requires_the_ai_permission():
    app.dependency_overrides[get_text_generator] = lambda: FakeGenerator()
    _permissions(*(p for p in ALL_PERMISSIONS if p != Permission.AI))

    assert client.post(f"{API}/pulse/interpretation", json={}).status_code == 403


def test_interpretation_without_key_is_503():
    app.dependency_overrides[get_text_generator] = lambda: None

    assert client.post(f"{API}/pulse/interpretation", json={}).status_code == 503


def test_interpretation_provider_failure_is_502():
    app.dependency_overrides[get_text_generator] = lambda: FakeGenerator(fail=True)

    assert client.post(f"{API}/pulse/interpretation", json={}).status_code == 502
