"""Speaking (/english/speech): transcripcion, diff de la lectura y consumo.

Nunca llaman a OpenAI: se reemplaza el transcriptor por uno falso.
"""

import pytest
from sqlalchemy import select

from app.api.deps import get_speech_transcriber
from app.core.config import settings
from app.db.models.ai_usage import AiUsageEvent
from app.db.models.english import EngWordContent
from app.integrations.speech_client import (
    VERBATIM_PROMPT,
    Transcription,
    TranscriptionError,
    extension_for,
)
from app.main import app
from app.services.english_reading_diff import compare_reading, tokens
from tests.conftest import client
from tests.english_fixtures import READING, seed_bank

URL = "/api/v1/english/speech"


class FakeTranscriber:
    def __init__(self) -> None:
        self.text = "I see the worda in the park."
        self.duration: float | None = 12.5
        self.fail = False
        self.calls: list[dict] = []

    def transcribe(self, *, audio: bytes, content_type: str, model: str) -> Transcription:
        self.calls.append({"audio": audio, "content_type": content_type, "model": model})
        if self.fail:
            raise TranscriptionError("RateLimitError")
        return Transcription(text=self.text, duration_seconds=self.duration)


@pytest.fixture
def transcriber() -> FakeTranscriber:
    fake = FakeTranscriber()
    app.dependency_overrides[get_speech_transcriber] = lambda: fake
    return fake


@pytest.fixture
def content_id(db_session) -> int:
    word = seed_bank(db_session, words=["worda"])[0]
    return db_session.execute(
        select(EngWordContent.id).where(EngWordContent.word_id == word.id)
    ).scalar_one()


def _post(content_id: int, phase: str, *, seconds: float = 10, mime: str = "audio/webm"):
    return client.post(
        URL,
        data={"content_id": str(content_id), "phase": phase, "duration_seconds": str(seconds)},
        files={"audio": ("speech.webm", b"fake-audio", mime)},
    )


# --- Diff de la lectura ---


def test_numbers_and_punctuation_do_not_count_as_errors():
    assert tokens("I have 21 cats, OK?") == ["i", "have", "twenty", "one", "cats", "ok"]
    diff = compare_reading("I have twenty-one cats.", "i have 21 cats")
    assert diff.match_pct == 100.0


def test_reading_diff_marks_missing_extra_and_changed_words():
    diff = compare_reading("The big dog runs fast.", "The dog run very fast")

    assert diff.match_pct == 60.0  # the, dog, fast de 5
    kinds = [(op.kind, op.expected, op.said) for op in diff.ops]
    assert ("missing", ["big"], []) in kinds
    assert ("changed", ["runs"], ["run", "very"]) in kinds


def test_audio_extension_ignores_codec_parameters():
    assert extension_for("audio/webm;codecs=opus") == "webm"
    assert extension_for("audio/mp4") == "mp4"
    assert extension_for("video/webm") is None


# --- Endpoint ---


def test_reading_is_transcribed_compared_and_recorded(db_session, transcriber, content_id):
    response = _post(content_id, "reading")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["transcript"] == "I see the worda in the park."
    assert body["duration_seconds"] == 12.5
    expected_words = len(tokens(READING.format(word="worda")))
    assert body["match_pct"] == round(100 * 7 / expected_words, 1)
    assert body["diff"][0] == {
        "kind": "equal",
        "expected": ["i", "see", "the", "worda", "in", "the", "park"],
        "said": ["i", "see", "the", "worda", "in", "the", "park"],
    }
    assert transcriber.calls == [
        {"audio": b"fake-audio", "content_type": "audio/webm", "model": "whisper-1"}
    ]

    event = db_session.execute(select(AiUsageEvent)).scalar_one()
    assert (event.feature, event.audio_seconds, event.user_id) == ("english.transcription", 12.5, 1)
    assert event.estimated_cost_usd == pytest.approx(12.5 / 60 * 0.006)


def test_free_speaking_has_no_diff_and_uses_client_duration_if_missing(
    db_session, transcriber, content_id
):
    transcriber.duration = None

    body = _post(content_id, "free", seconds=20).json()

    assert body["match_pct"] is None
    assert body["diff"] is None
    assert body["duration_seconds"] == 20


def test_recordings_over_the_level_limit_are_rejected_before_paying(transcriber, content_id):
    # A1: 30 s de speaking libre (+10 de margen).
    response = _post(content_id, "free", seconds=45)

    assert response.status_code == 422
    assert transcriber.calls == []


def test_unsupported_or_oversized_audio_is_rejected(monkeypatch, transcriber, content_id):
    assert _post(content_id, "free", mime="video/mp4").status_code == 422
    monkeypatch.setattr(settings, "english_max_audio_bytes", 4)
    assert _post(content_id, "free").status_code == 422
    assert transcriber.calls == []


def test_unknown_content_is_404(transcriber):
    assert _post(99999, "reading").status_code == 404


def test_without_openai_key_is_503(content_id):
    app.dependency_overrides[get_speech_transcriber] = lambda: None

    assert _post(content_id, "reading").status_code == 503


def test_provider_failure_is_502_and_nothing_is_recorded(db_session, transcriber, content_id):
    transcriber.fail = True

    assert _post(content_id, "reading").status_code == 502
    assert db_session.execute(select(AiUsageEvent)).first() is None


def test_the_expected_text_is_never_sent_as_prompt():
    # El prompt fijo solo tiene muletillas (C1): nada del texto de lectura.
    assert "park" not in VERBATIM_PROMPT
    assert "umm" in VERBATIM_PROMPT.lower()
