"""Sugerencia de cambio de nivel (ENGLISH-TEACHER-PLAN.md, seccion 4.1): reglas
sobre las ultimas 10 practicas, "no por ahora" y nivel dominado (D19)."""

import pytest

from app.core.config import settings
from app.db.models.english import EngPractice
from app.services.english_level_suggestion import WINDOW, suggest
from app.services.english_levels import EnglishLevel
from tests.conftest import client
from tests.english_fixtures import practice_payload, seed_bank

API = "/api/v1/english"
A1, A2, B1 = EnglishLevel.A1, EnglishLevel.A2, EnglishLevel.B1


def fake(revealed: bool = False, text_shown: bool = False, reading: float | None = 95):
    return EngPractice(
        vocab_revealed=revealed, listening_text_shown=text_shown, reading_match_pct=reading
    )


# --- Reglas ---


def test_strong_practices_suggest_moving_up():
    result = suggest(
        level=A1,
        practices=[fake()] * WINDOW,
        level_completed=False,
        dismissed=False,
        available={A1, A2},
    )

    assert (result.direction, result.level, result.reason) == ("up", A2, "performance")


def test_moving_up_needs_the_three_signals():
    # 7 de 10 sin revelar (70%) no llega al 80%.
    practices = [fake()] * 7 + [fake(revealed=True)] * 3
    assert (
        suggest(
            level=A1,
            practices=practices,
            level_completed=False,
            dismissed=False,
            available={A1, A2},
        )
        is None
    )
    # Sin ninguna lectura grabada tampoco se sugiere subir.
    assert (
        suggest(
            level=A1,
            practices=[fake(reading=None)] * WINDOW,
            level_completed=False,
            dismissed=False,
            available={A1, A2},
        )
        is None
    )


def test_two_weak_signals_suggest_moving_down():
    practices = [fake(revealed=True, text_shown=True, reading=None)] * WINDOW

    result = suggest(
        level=A2, practices=practices, level_completed=False, dismissed=False, available={A1, A2}
    )

    assert (result.direction, result.level) == ("down", A1)


def test_no_suggestion_without_a_full_window_or_an_available_target():
    assert (
        suggest(
            level=A1,
            practices=[fake()] * 9,
            level_completed=False,
            dismissed=False,
            available={A1, A2},
        )
        is None
    )
    assert (
        suggest(
            level=A1,
            practices=[fake()] * WINDOW,
            level_completed=False,
            dismissed=False,
            available={A1},
        )
        is None
    )


def test_completing_the_level_suggests_moving_up_unless_dismissed():
    completed = suggest(
        level=A1, practices=[], level_completed=True, dismissed=False, available={A1, A2}
    )
    assert (completed.direction, completed.reason) == ("up", "completed")
    assert (
        suggest(level=A1, practices=[], level_completed=True, dismissed=True, available={A1, A2})
        is None
    )


# --- API ---


@pytest.fixture(autouse=True)
def small_bank(monkeypatch):
    monkeypatch.setattr(settings, "english_min_words_per_level", 1)


def _practice(**overrides) -> None:
    practice = client.get(f"{API}/practices/next").json()
    payload = practice_payload(practice, mastered=False, **overrides)
    assert client.post(f"{API}/practices", json=payload).status_code == 201


def _suggestion():
    return client.get(f"{API}/settings").json()["suggestion"]


def test_suggestion_appears_after_ten_strong_practices_and_can_be_dismissed(db_session):
    seed_bank(db_session, level="A1", words=["alpha", "bravo", "charlie"])
    seed_bank(db_session, level="A2", words=["delta"])
    client.put(f"{API}/settings", json={"level": "A1"})

    for _ in range(WINDOW - 1):
        _practice(reading_match_pct=95)
    assert _suggestion() is None

    _practice(reading_match_pct=95)
    assert _suggestion() == {"direction": "up", "level": "A2", "reason": "performance"}

    dismissed = client.post(f"{API}/settings/level-suggestion/dismiss").json()
    assert dismissed["suggestion"] is None
    # Hacen falta 10 practicas nuevas para volver a sugerir.
    for _ in range(WINDOW - 1):
        _practice(reading_match_pct=95)
    assert _suggestion() is None
    _practice(reading_match_pct=95)
    assert _suggestion()["level"] == "A2"


def test_changing_level_resets_the_suggestion(db_session):
    seed_bank(db_session, level="A1", words=["alpha", "bravo"])
    seed_bank(db_session, level="A2", words=["delta", "echo"])
    client.put(f"{API}/settings", json={"level": "A1"})
    for _ in range(WINDOW):
        _practice(reading_match_pct=95)

    settings_a2 = client.put(f"{API}/settings", json={"level": "A2"}).json()

    # Las practicas de A1 no cuentan para A2.
    assert settings_a2["suggestion"] is None


def test_mastering_the_level_suggests_moving_up(db_session):
    seed_bank(db_session, level="A1", words=["alpha"])
    seed_bank(db_session, level="A2", words=["delta"])
    client.put(f"{API}/settings", json={"level": "A1"})
    practice = client.get(f"{API}/practices/next").json()
    client.post(f"{API}/practices", json=practice_payload(practice, mastered=True))

    body = client.get(f"{API}/settings").json()

    assert body["level_completed"] is True
    assert body["suggestion"] == {"direction": "up", "level": "A2", "reason": "completed"}


def test_dismiss_without_level_is_409():
    assert client.post(f"{API}/settings/level-suggestion/dismiss").status_code == 409
