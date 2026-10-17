"""Practica de ingles (/english): nivel, seleccion de palabra, guardado al cierre
y check "la domino" (ENGLISH-TEACHER-PLAN.md, D4/D8/D19/D20/D21)."""

import random

import pytest
from fastapi import Depends
from sqlalchemy import select

from app.api.deps import get_english_practice_repository, get_english_practice_service
from app.core.config import settings
from app.db.models.english import EngPractice, EngUserWord
from app.main import app
from app.services.english_practice_service import EnglishPracticeService
from tests.conftest import OTHER_USER_ID, acting_as, client
from tests.english_fixtures import practice_payload, seed_bank

API = "/api/v1/english"


class FixedRandom(random.Random):
    """random() fijo: 0.0 = siempre repaso primero, 0.99 = siempre nueva primero."""

    def __init__(self, value: float) -> None:
        super().__init__(0)
        self.value = value

    def random(self) -> float:
        return self.value


@pytest.fixture(autouse=True)
def small_bank(monkeypatch):
    """Los tests siembran pocas palabras: cualquier nivel con una ya se puede elegir."""
    monkeypatch.setattr(settings, "english_min_words_per_level", 1)


def use_rng(value: float) -> None:
    def override(repository=Depends(get_english_practice_repository)):
        return EnglishPracticeService(
            repository,
            min_words_per_level=settings.english_min_words_per_level,
            rng=FixedRandom(value),
        )

    app.dependency_overrides[get_english_practice_service] = override


def _set_level(level: str = "A1") -> None:
    assert client.put(f"{API}/settings", json={"level": level}).status_code == 200


def _complete(**overrides) -> dict:
    practice = client.get(f"{API}/practices/next").json()
    response = client.post(f"{API}/practices", json=practice_payload(practice, **overrides))
    assert response.status_code == 201, response.text
    return {"practice": practice, "saved": response.json()}


# --- Nivel ---


def test_settings_start_without_level_and_list_availability(db_session):
    seed_bank(db_session, level="A1")

    body = client.get(f"{API}/settings").json()

    assert body["level"] is None
    assert body["level_completed"] is False
    by_level = {row["level"]: row for row in body["levels"]}
    assert by_level["A1"] == {"level": "A1", "ready_words": 6, "available": True}
    assert by_level["B1"] == {"level": "B1", "ready_words": 0, "available": False}


def test_a_level_without_bank_cannot_be_chosen(db_session, monkeypatch):
    monkeypatch.setattr(settings, "english_min_words_per_level", 5)
    seed_bank(db_session, level="A1", words=["one", "two"])  # menos del minimo

    response = client.put(f"{API}/settings", json={"level": "A1"})

    assert response.status_code == 422


def test_practice_requires_a_level(db_session):
    seed_bank(db_session)

    assert client.get(f"{API}/practices/next").status_code == 409


# --- Seleccion ---


def test_next_practice_returns_everything_including_the_answer(db_session):
    seed_bank(db_session)
    _set_level()

    practice = client.get(f"{API}/practices/next").json()

    assert practice["lemma"].startswith("word")
    assert practice["image"]["url"] == f"https://img.example/{practice['lemma']}.png"
    assert practice["reading_text"].startswith(practice["listening_sentence"])
    assert practice["writing_prompt_es"]
    assert practice["mastered_repeat"] is False
    assert practice["config"] == {
        "first_letter_hint": True,
        "tts_rate": 0.8,
        "writing_min_chars": 30,
        "free_speaking_seconds": 30,
        "instructions_lang": "es",
    }
    # Pedirla no guarda nada (D8).
    assert db_session.execute(select(EngPractice)).first() is None


def test_never_repeats_the_previous_word(db_session):
    seed_bank(db_session, words=["alpha", "bravo"])
    use_rng(0.0)  # repaso primero
    _set_level()

    first = _complete(mastered=False)["practice"]["lemma"]
    second = client.get(f"{API}/practices/next").json()["lemma"]

    assert first != second


def test_mixes_unmastered_words_back_in(db_session):
    seed_bank(db_session, words=["alpha", "bravo", "charlie"])
    _set_level()
    use_rng(0.99)  # nueva primero
    first = _complete(mastered=False)["practice"]["lemma"]
    _complete(mastered=True)  # otra nueva, dominada

    use_rng(0.0)  # repaso primero: vuelve la no dominada
    assert client.get(f"{API}/practices/next").json()["lemma"] == first


def test_mastered_words_do_not_come_back_until_the_level_is_done(db_session):
    seed_bank(db_session, words=["alpha", "bravo"])
    _set_level()
    use_rng(0.99)
    first = _complete(mastered=True)["practice"]["lemma"]

    second = client.get(f"{API}/practices/next").json()
    assert second["lemma"] != first
    assert client.get(f"{API}/settings").json()["level_completed"] is False

    client.post(f"{API}/practices", json=practice_payload(second, mastered=True))

    # Domino todo (D19): se repiten las dominadas y la UI lo sabe.
    repeat = client.get(f"{API}/practices/next").json()
    assert repeat["mastered_repeat"] is True
    assert repeat["lemma"] == first
    assert client.get(f"{API}/settings").json()["level_completed"] is True


# --- Guardado y check ---


def test_save_practice_stores_it_and_marks_the_word(db_session):
    seed_bank(db_session)
    _set_level()

    result = _complete(vocab_revealed=False, mastered=True)

    assert result["saved"]["mastered"] is True
    assert result["saved"]["was_mastered"] is False
    practice = db_session.get(EngPractice, result["saved"]["id"])
    assert (practice.level, practice.audio_seconds, practice.user_id) == ("A1", 42.0, 1)
    user_word = db_session.get(EngUserWord, (1, result["practice"]["word_id"]))
    assert user_word.mastered is True
    assert user_word.times_practiced == 1
    assert user_word.mastered_at is not None


def test_check_can_be_changed_after_saving(db_session):
    seed_bank(db_session)
    _set_level()
    result = _complete(mastered=True)
    practice_id = result["saved"]["id"]

    response = client.patch(f"{API}/practices/{practice_id}", json={"mastered": False})

    assert response.json()["mastered"] is False
    user_word = db_session.get(EngUserWord, (1, result["practice"]["word_id"]))
    assert (user_word.mastered, user_word.mastered_at) == (False, None)


def test_a_mastered_word_cannot_be_unmarked(db_session):
    seed_bank(db_session, words=["alpha"])
    _set_level()
    _complete(mastered=True)

    repeat = _complete(mastered=False)  # se repite (D19) y el check no aplica (D20)

    assert repeat["saved"] == {"id": repeat["saved"]["id"], "mastered": True, "was_mastered": True}
    patched = client.patch(f"{API}/practices/{repeat['saved']['id']}", json={"mastered": False})
    assert patched.json()["mastered"] is True


def test_writing_shorter_than_the_level_minimum_is_rejected(db_session):
    seed_bank(db_session)
    _set_level()
    practice = client.get(f"{API}/practices/next").json()

    response = client.post(
        f"{API}/practices", json=practice_payload(practice, writing_text="short")
    )

    assert response.status_code == 422


def test_content_must_belong_to_the_word(db_session):
    words = seed_bank(db_session, words=["alpha", "bravo"])
    _set_level()
    practice = client.get(f"{API}/practices/next").json()
    other = next(w for w in words if w.id != practice["word_id"])

    response = client.post(f"{API}/practices", json=practice_payload(practice, word_id=other.id))

    assert response.status_code == 422


# --- Aislamiento ---


def test_users_do_not_share_settings_or_mastered_words(db_session, other_user):
    seed_bank(db_session, words=["alpha"])
    _set_level()
    _complete(mastered=True)

    with acting_as(OTHER_USER_ID):
        assert client.get(f"{API}/settings").json()["level"] is None
        _set_level()
        practice = client.get(f"{API}/practices/next").json()
        # Para B la palabra es nueva: lo que domina A no le afecta.
        assert practice["mastered_repeat"] is False


def test_a_user_cannot_change_another_users_practice(db_session, other_user):
    seed_bank(db_session)
    with acting_as(OTHER_USER_ID):
        _set_level()
        practice_id = _complete(mastered=True)["saved"]["id"]

    assert (
        client.patch(f"{API}/practices/{practice_id}", json={"mastered": False}).status_code == 404
    )
    user_word = db_session.execute(
        select(EngUserWord).where(EngUserWord.user_id == OTHER_USER_ID)
    ).scalar_one()
    assert user_word.mastered is True
