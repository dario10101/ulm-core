"""Feedback de una practica (/english/practices/{id}/feedback) y memoria del
usuario (ENGLISH-TEACHER-PLAN.md, 7.2). Nunca llaman a OpenAI."""

import json

import pytest
from sqlalchemy import select

from app.api.deps import get_text_generator
from app.core.config import settings
from app.db.models.ai_usage import AiUsageEvent
from app.db.models.english import EngPracticeFeedback, EngUserMemory
from app.integrations.openai_client import GeneratedText, TextGenerationError
from app.main import app
from tests.conftest import OTHER_USER_ID, acting_as, client
from tests.english_fixtures import practice_payload, seed_bank

API = "/api/v1/english"

FEEDBACK = {
    "summary": "Buen trabajo.",
    "vocabulary": "Sabías la palabra.",
    "writing_corrections": [
        {"original": "I has a dog", "corrected": "I have a dog", "explanation": "Con I va have."}
    ],
    "reading_observations": ["Omitiste 'very'."],
    "speaking_corrections": [],
    "answered_question": True,
    "tips": ["Repasa el verbo have."],
    "memory_update": "Confuses has/have. Reads fluently.",
}


class FakeGenerator:
    def __init__(self) -> None:
        self.text = json.dumps(FEEDBACK)
        self.fail = False
        self.calls: list[dict] = []

    def generate(self, **kwargs) -> GeneratedText:
        self.calls.append(kwargs)
        if self.fail:
            raise TextGenerationError("APIConnectionError")
        return GeneratedText(
            text=self.text, model=kwargs["model"], input_tokens=800, output_tokens=300
        )

    def available_models(self) -> frozenset[str]:
        return frozenset()


@pytest.fixture
def generator() -> FakeGenerator:
    fake = FakeGenerator()
    app.dependency_overrides[get_text_generator] = lambda: fake
    return fake


@pytest.fixture(autouse=True)
def small_bank(monkeypatch):
    monkeypatch.setattr(settings, "english_min_words_per_level", 1)


def _practice(db_session, **overrides) -> int:
    seed_bank(db_session, words=["dogs"])
    client.put(f"{API}/settings", json={"level": "A1"})
    practice = client.get(f"{API}/practices/next").json()
    payload = practice_payload(
        practice, writing_text="I has a dog and it is very nice.", **overrides
    )
    return client.post(f"{API}/practices", json=payload).json()["id"]


def test_feedback_is_generated_saved_and_updates_the_memory(db_session, generator):
    practice_id = _practice(db_session)

    response = client.post(f"{API}/practices/{practice_id}/feedback")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"] == "Buen trabajo."
    assert body["writing_corrections"][0]["corrected"] == "I have a dog"
    assert body["model"] == settings.english_model
    assert "memory_update" not in body  # interno: no va al cliente

    call = generator.calls[0]
    assert call["json_schema"]["title"] == "english_practice_feedback"
    assert call["max_output_tokens"] == settings.english_feedback_max_output_tokens
    assert "I has a dog and it is very nice." in call["prompt"]
    assert "Previous learner memory: (none yet)" in call["prompt"]
    # A1: feedback en español.
    assert "in Spanish" in call["instructions"]

    memory = db_session.get(EngUserMemory, 1)
    assert memory.summary == "Confuses has/have. Reads fluently."
    assert db_session.get(EngPracticeFeedback, practice_id).input_tokens == 800
    event = db_session.execute(select(AiUsageEvent)).scalar_one()
    assert event.feature == "english.feedback"


def test_asking_again_returns_the_saved_feedback_without_paying(db_session, generator):
    practice_id = _practice(db_session)
    first = client.post(f"{API}/practices/{practice_id}/feedback").json()

    second = client.post(f"{API}/practices/{practice_id}/feedback").json()

    assert first == second
    assert len(generator.calls) == 1


def test_the_memory_is_sent_in_the_next_feedback(db_session, generator):
    db_session.add(EngUserMemory(user_id=1, summary="Forgets articles."))
    db_session.commit()
    practice_id = _practice(db_session)

    client.post(f"{API}/practices/{practice_id}/feedback")

    assert "Previous learner memory: Forgets articles." in generator.calls[0]["prompt"]
    assert db_session.get(EngUserMemory, 1).summary == "Confuses has/have. Reads fluently."


def test_reading_diff_is_computed_before_calling_the_llm(db_session, generator):
    practice_id = _practice(db_session, reading_transcript="I see the dogs in park")

    client.post(f"{API}/practices/{practice_id}/feedback")

    assert "missing: expected 'the' said ''" in generator.calls[0]["prompt"]


def test_an_invalid_response_is_502_but_the_cost_is_recorded(db_session, generator):
    practice_id = _practice(db_session)
    generator.text = "not json"

    response = client.post(f"{API}/practices/{practice_id}/feedback")

    assert response.status_code == 502
    assert db_session.get(EngPracticeFeedback, practice_id) is None
    assert db_session.execute(select(AiUsageEvent)).scalar_one().feature == "english.feedback"


def test_provider_failure_is_502(db_session, generator):
    practice_id = _practice(db_session)
    generator.fail = True

    assert client.post(f"{API}/practices/{practice_id}/feedback").status_code == 502


def test_without_openai_key_is_503(db_session):
    practice_id = _practice(db_session)
    app.dependency_overrides[get_text_generator] = lambda: None

    assert client.post(f"{API}/practices/{practice_id}/feedback").status_code == 503


def test_feedback_of_another_users_practice_is_404(db_session, generator, other_user):
    seed_bank(db_session, words=["dogs"])
    with acting_as(OTHER_USER_ID):
        client.put(f"{API}/settings", json={"level": "A1"})
        practice = client.get(f"{API}/practices/next").json()
        practice_id = client.post(f"{API}/practices", json=practice_payload(practice)).json()["id"]

    assert client.post(f"{API}/practices/{practice_id}/feedback").status_code == 404
    assert generator.calls == []


def test_the_dictation_goes_in_the_prompt(db_session, generator):
    practice_id = _practice(db_session, dictation_text="I see the dog in park")

    body = client.post(f"{API}/practices/{practice_id}/feedback").json()

    prompt = generator.calls[0]["prompt"]
    assert "Dictation (wrote the listening sentence): I see the dog in park" in prompt
    assert "Dictation diff: match" in prompt
    assert body["dictation"] == ""  # el falso no lo trae: vale el default


def test_feedback_saved_before_the_dictation_still_loads(db_session, generator):
    practice_id = _practice(db_session)
    old = {k: v for k, v in FEEDBACK.items() if k != "dictation"}
    db_session.add(
        EngPracticeFeedback(
            practice_id=practice_id, feedback=old, model="m", input_tokens=1, output_tokens=1
        )
    )
    db_session.commit()

    response = client.post(f"{API}/practices/{practice_id}/feedback")

    assert response.status_code == 200
    assert response.json()["dictation"] == ""
    assert generator.calls == []
