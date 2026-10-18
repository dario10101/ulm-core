"""Banco compartido de ingles (/system/english, solo admin): lista de palabras,
validacion del contenido, llenado idempotente por lotes y curacion posterior.

Nunca llaman a OpenAI ni a las fuentes de imagenes: se reemplazan por falsos.
"""

import json

import pytest
from sqlalchemy import select

from app.api.deps import get_image_search, get_text_generator
from app.core.config import settings
from app.db.models.ai_usage import AiUsageEvent
from app.db.models.english import EngWord, EngWordContent, EngWordImage
from app.integrations.image_search import (
    ImageCandidate,
    ImageSearchError,
    MultiSourceImageSearch,
)
from app.integrations.openai_client import GeneratedText, TextGenerationError
from app.main import app
from app.services.english_content import (
    GeneratedItem,
    contains_word,
    filter_accepted_answers,
    validate_hint,
    validate_item,
)
from app.services.english_levels import EnglishLevel, level_config
from app.services.english_wordlist import load_word_list, parse_rows
from tests.conftest import client

API = "/api/v1/system/english"


# --- Falsos ---


class FakeImageSearch:
    def __init__(self) -> None:
        # Palabras sin imagen en ninguna fuente.
        self.missing: set[str] = set()
        self.calls: list[str] = []

    def find(self, word: str, *, pos: str, limit: int) -> list[ImageCandidate]:
        self.calls.append(word)
        if word in self.missing:
            return []
        return [
            ImageCandidate(
                url=f"https://img.example/{word}/{i}.png",
                source="arasaac",
                license="CC BY-NC-SA 4.0",
                attribution="ARASAAC",
                page_url=None,
            )
            for i in range(3)
        ]


def good_item(word: str, level: EnglishLevel = EnglishLevel.A1) -> dict:
    listening = f"I see the {word} in the park."
    item = {
        "word": word,
        "accepted_answers": [],
        "listening_sentence": listening,
        "writing_prompt": f"Write where you see a {word}.",
        "writing_prompt_es": f"Escribe donde ves un {word}."
        if level in (EnglishLevel.A1, EnglishLevel.A2)
        else "",
        "reading_text": f"{listening} It is very nice today. Do you like the park?",
        "hint": "Mira bien la imagen."
        if level in (EnglishLevel.A1, EnglishLevel.A2)
        else "An animal that lives in the park.",
        "translation_es": "perro",
    }
    return item


class FakeGenerator:
    """Devuelve contenido valido para cada palabra del prompt, salvo las de `broken`."""

    def __init__(self) -> None:
        self.broken: set[str] = set()
        self.fail = False
        self.calls: list[dict] = []

    def generate(self, **kwargs) -> GeneratedText:
        self.calls.append(kwargs)
        if self.fail:
            raise TextGenerationError("RateLimitError: sin saldo")
        words = [line[2:].split(" (")[0] for line in kwargs["prompt"].splitlines()[1:]]
        items = []
        for word in words:
            item = good_item(word)
            if word in self.broken:
                item["listening_sentence"] = "This sentence forgets the word."
            items.append(item)
        return GeneratedText(
            text=json.dumps({"items": items}),
            model=kwargs["model"],
            input_tokens=1000,
            output_tokens=2000,
        )

    def available_models(self) -> frozenset[str]:
        return frozenset()


@pytest.fixture(autouse=True)
def as_admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "ruben@example.com")


@pytest.fixture
def images() -> FakeImageSearch:
    fake = FakeImageSearch()
    app.dependency_overrides[get_image_search] = lambda: fake
    return fake


@pytest.fixture
def generator() -> FakeGenerator:
    fake = FakeGenerator()
    app.dependency_overrides[get_text_generator] = lambda: fake
    return fake


def _level(level: str = "A1") -> dict:
    return next(row for row in client.get(f"{API}/levels").json() if row["level"] == level)


def _fill(level: str = "A1") -> list[dict]:
    """Lo que hace el front con "Fill bank": importar y procesar hasta terminar."""
    client.post(f"{API}/levels/{level}/import")
    progress = []
    while True:
        response = client.post(f"{API}/levels/{level}/process")
        assert response.status_code == 200, response.text
        progress.append(response.json())
        if response.json()["remaining"] == 0:
            return progress


# --- Lista de palabras (D28/D29) ---


def test_word_list_keeps_lowercase_nouns_verbs_and_adjectives():
    entries = parse_rows(
        [
            ("apple", "noun", "A1", "cefrj"),
            ("TV", "noun", "A1", "cefrj"),
            ("quickly", "adverb", "A2", "cefrj"),
            ("of", "preposition", "A1", "cefrj"),
            ("ice cream", "noun", "A1", "cefrj"),
            ("go", "verb", "A1", "cefrj"),  # muy corta
        ]
    )

    assert {e.lemma for e in entries} == {"apple", "ice cream"}


def test_word_list_prefers_noun_and_the_lowest_level():
    entries = parse_rows(
        [
            ("light", "adjective", "A1", "cefrj"),
            ("light", "noun", "A2", "cefrj"),
            ("color/colour", "noun", "A1", "cefrj"),
        ]
    )
    by_lemma = {e.lemma: e for e in entries}

    assert by_lemma["light"].pos == "noun"
    assert by_lemma["light"].level == EnglishLevel.A1
    assert by_lemma["color"].variants == ("colour",)


def test_real_word_list_has_words_in_every_level_without_duplicates():
    entries = load_word_list()
    lemmas = [e.lemma for e in entries]

    assert len(lemmas) == len(set(lemmas))
    assert {e.level for e in entries} == set(EnglishLevel)
    assert {e.pos for e in entries} == {"noun", "verb", "adjective"}


# --- Validacion del contenido ---


def test_valid_item_extracts_the_final_question():
    content = validate_item(GeneratedItem(**good_item("dog")), "dog", level_config(EnglishLevel.A1))

    assert not isinstance(content, str)
    assert content.reading_question == "Do you like the park?"
    assert content.writing_prompt_es == "Escribe donde ves un dog."
    assert content.hint == "Mira bien la imagen."


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"listening_sentence": "I like the park a lot."}, "word_missing_in_sentence"),
        (
            {"reading_text": "Something else. Do you like it?"},
            "reading_does_not_start_with_listening",
        ),
        (
            {"reading_text": "I see the dog in the park. It is nice. I like it."},
            "reading_without_final_question",
        ),
        ({"writing_prompt_es": ""}, "missing_spanish_prompt"),
        ({"hint": ""}, "empty_hint"),
        ({"hint": "Your pet dog."}, "hint_contains_word"),
        ({"hint": "Un perro pequeño."}, "hint_contains_translation"),
    ],
)
def test_invalid_items_are_rejected_with_a_reason(change, reason):
    item = GeneratedItem(**{**good_item("dog"), **change})

    assert validate_item(item, "dog", level_config(EnglishLevel.A1)) == reason


def test_spanish_prompt_is_dropped_above_a2():
    item = GeneratedItem(**{**good_item("dog", EnglishLevel.B1), "writing_prompt_es": "Hola"})
    item.listening_sentence = "Yesterday I saw a very friendly dog in the big park."
    item.reading_text = f"{item.listening_sentence} It ran to me. It was happy. Do you have a pet?"

    content = validate_item(item, "dog", level_config(EnglishLevel.B1))

    assert not isinstance(content, str)
    assert content.writing_prompt_es is None


def test_hint_must_not_give_away_the_word_or_its_synonyms():
    assert validate_hint("Un animal que ladra.", "dog", []) is None
    assert validate_hint("Many dogs live here.", "dog", []) == "hint_contains_word"
    assert validate_hint("A puppy is a young one.", "dog", ["puppy"]) == "hint_contains_word"
    assert validate_hint("x" * 121, "dog", []) == "hint_too_long"


def test_hint_must_not_give_away_the_spanish_translation():
    # Sin tildes ni mayusculas, y tambien en plural.
    assert validate_hint("Cuerda gruesa para atar.", "rope", [], "cuerda") == (
        "hint_contains_translation"
    )
    assert validate_hint("Aparato con cámaras.", "camera", [], "camara") == (
        "hint_contains_translation"
    )
    # Las palabras cortas de la traduccion no cuentan.
    assert (
        validate_hint("Lugar de la casa para descansar.", "sitting room", [], "sala de estar")
        is None
    )


def test_bank_instructions_ask_for_a_spanish_hint_only_in_basic_levels():
    from app.services.english_content import build_instructions

    assert "hint: one short clue in Spanish" in build_instructions(EnglishLevel.A2)
    assert "hint: one short clue in simple English" in build_instructions(EnglishLevel.B1)


def test_regular_inflections_count_as_the_word():
    assert contains_word("She studies every day.", "study")
    assert contains_word("They were running fast.", "run")
    assert contains_word("I like ice cream.", "ice cream")
    assert not contains_word("We went home.", "go")


def test_accepted_answers_must_fit_the_boxes():
    assert filter_accepted_answers("color", ["colour", "Shade", "hue", "color", "c-lor"]) == [
        "shade"
    ]
    assert filter_accepted_answers("t-shirt", ["t shirt", "tee-shirt", "v-necks"]) == ["v-necks"]


# --- Llenado ---


def test_import_adds_the_next_batch_without_duplicates(db_session):
    first = client.post(f"{API}/levels/A1/import").json()["added"]
    second = client.post(f"{API}/levels/A1/import").json()["added"]

    assert first == second == 100
    lemmas = db_session.execute(select(EngWord.lemma)).scalars().all()
    assert len(lemmas) == len(set(lemmas)) == 200
    status = _level()
    assert status["imported"] == 200
    assert status["pending"] == 200
    assert status["full"] is False


def test_fill_approves_words_with_image_and_valid_content(db_session, images, generator):
    progress = _fill()

    assert len(progress) == 10  # 100 palabras en lotes de 10
    assert sum(p["approved"] for p in progress) == 100
    assert len(generator.calls) == 10
    call = generator.calls[0]
    assert call["model"] == settings.english_model
    assert call["max_output_tokens"] == settings.english_bank_max_output_tokens
    assert call["json_schema"]["title"] == "english_bank_batch"

    word = db_session.execute(select(EngWord).limit(1)).scalar_one()
    assert word.status == "APPROVED"
    content = db_session.execute(
        select(EngWordContent).where(EngWordContent.word_id == word.id)
    ).scalar_one()
    assert content.level == "A1"
    assert content.hint == "Mira bien la imagen."
    assert content.prompt_version == 2
    assert content.reading_question.endswith("?")
    selected = db_session.execute(
        select(EngWordImage).where(EngWordImage.word_id == word.id, EngWordImage.selected)
    ).scalar_one()
    assert selected.position == 0

    # Cada llamada al LLM queda registrada a nombre del admin.
    events = db_session.execute(select(AiUsageEvent)).scalars().all()
    assert len(events) == 10
    assert {e.feature for e in events} == {"english.bank"}
    assert all(e.user_id == 1 and e.estimated_cost_usd > 0 for e in events)

    assert _level()["approved"] == 100


def test_failures_go_to_review_and_are_retried_once(db_session, images, generator):
    client.post(f"{API}/levels/A1/import")
    lemmas = db_session.execute(select(EngWord.lemma).order_by(EngWord.id)).scalars().all()
    images.missing = {lemmas[0]}
    generator.broken = {lemmas[1]}

    _fill()

    words = {w.lemma: w for w in db_session.execute(select(EngWord)).scalars()}
    assert (words[lemmas[0]].status, words[lemmas[0]].status_reason) == ("REVIEW", "no_image")
    assert words[lemmas[1]].status_reason == "word_missing_in_sentence"
    # Un reintento y despues queda para el admin.
    assert words[lemmas[0]].fill_attempts == words[lemmas[1]].fill_attempts == 2
    status = _level()
    assert (status["approved"], status["review"], status["processable"]) == (198, 2, 0)


def test_filling_again_does_not_regenerate_existing_content(db_session, images, generator):
    _fill()
    calls_before = len(generator.calls)
    searches_before = len(images.calls)

    progress = _fill()  # importa las 100 siguientes

    assert sum(p["approved"] for p in progress) == 100
    # Solo las nuevas: lo aprobado no se vuelve a buscar ni a generar.
    assert len(generator.calls) - calls_before == 10
    assert len(images.calls) - searches_before == 100


def test_a_level_is_full_when_the_list_is_exhausted(monkeypatch, images, generator):
    from app.services import english_bank_service

    entries = [e for e in load_word_list() if e.level == EnglishLevel.C2][:15]
    monkeypatch.setattr(english_bank_service, "entries_for_level", lambda level: entries)

    _fill("C2")
    _fill("C2")
    status = _level("C2")

    assert (status["list_total"], status["imported"], status["full"]) == (15, 15, True)
    # Volver a llenar un banco lleno no hace nada (D25).
    assert client.post(f"{API}/levels/C2/import").json() == {"added": 0}
    assert client.post(f"{API}/levels/C2/process").json()["processed"] == 0


def test_process_without_openai_key_is_503(images):
    app.dependency_overrides[get_text_generator] = lambda: None
    client.post(f"{API}/levels/A1/import")

    assert client.post(f"{API}/levels/A1/process").status_code == 503


def test_provider_failure_is_502_and_nothing_is_saved(db_session, images, generator):
    client.post(f"{API}/levels/A1/import")
    generator.fail = True

    assert client.post(f"{API}/levels/A1/process").status_code == 502
    assert db_session.execute(select(EngWordImage)).first() is None
    assert _level()["pending"] == 100


# --- Curacion posterior (D24) ---


def _first_word_id() -> int:
    return client.get(f"{API}/words", params={"level": "A1"}).json()["items"][0]["id"]


def test_words_list_shows_image_and_status(images, generator):
    _fill()

    page = client.get(f"{API}/words", params={"level": "A1", "limit": 5}).json()

    assert page["total"] == 100
    assert len(page["items"]) == 5
    item = page["items"][0]
    assert item["status"] == "APPROVED"
    assert item["image"]["url"].endswith("/0.png")
    assert item["has_content"] is True
    assert client.get(f"{API}/words", params={"level": "A1", "status": "REVIEW"}).json() == {
        "items": [],
        "total": 0,
    }


def test_next_image_cycles_until_no_candidates_remain(images, generator):
    _fill()
    word_id = _first_word_id()

    assert (
        client.post(f"{API}/words/{word_id}/next-image").json()["image"]["url"].endswith("/1.png")
    )
    assert (
        client.post(f"{API}/words/{word_id}/next-image").json()["image"]["url"].endswith("/2.png")
    )
    response = client.post(f"{API}/words/{word_id}/next-image")
    assert response.status_code == 409
    # El 409 revierte: la imagen actual sigue elegida.
    words = client.get(f"{API}/words", params={"level": "A1"}).json()["items"]
    assert next(w for w in words if w["id"] == word_id)["image"]["url"].endswith("/2.png")


def test_disable_and_enable_a_word(images, generator):
    _fill()
    word_id = _first_word_id()

    disabled = client.patch(f"{API}/words/{word_id}", json={"status": "DISABLED"}).json()
    enabled = client.patch(f"{API}/words/{word_id}", json={"status": "APPROVED"}).json()

    assert (disabled["status"], enabled["status"]) == ("DISABLED", "APPROVED")
    assert client.patch(f"{API}/words/999999", json={"status": "DISABLED"}).status_code == 404


def test_a_word_without_content_cannot_be_approved(db_session):
    client.post(f"{API}/levels/A1/import")
    word_id = _first_word_id()

    response = client.patch(f"{API}/words/{word_id}", json={"status": "APPROVED"})

    assert response.status_code == 422


def test_non_admin_gets_403(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "otra@example.com")

    assert client.get(f"{API}/levels").status_code == 403
    assert client.post(f"{API}/levels/A1/import").status_code == 403


# --- Orden de las fuentes de imagenes ---


class FakeSource:
    def __init__(self, name: str, results: int = 0, fail: bool = False) -> None:
        self.name = name
        self.results = results
        self.fail = fail
        self.calls = 0

    def search(self, query: str, *, limit: int) -> list[ImageCandidate]:
        self.calls += 1
        if self.fail:
            raise ImageSearchError(f"{self.name} caido")
        return [
            ImageCandidate(
                url=f"https://{self.name}/{query}/{i}.png",
                source=self.name,
                license="x",
                attribution="x",
                page_url=None,
            )
            for i in range(min(self.results, limit))
        ]


def _search(arasaac: FakeSource, openverse: FakeSource, pexels: FakeSource | None = None):
    return MultiSourceImageSearch(arasaac=arasaac, openverse=openverse, pexels=pexels)


def test_openverse_is_not_used_to_complete_candidates():
    arasaac, openverse = FakeSource("arasaac", results=2), FakeSource("openverse", results=5)

    found = _search(arasaac, openverse).find("run", pos="verb", limit=5)

    # Solo 2 candidatas, pero Openverse no se consulta (cupo de 200/dia).
    assert [c.source for c in found] == ["arasaac", "arasaac"]
    assert openverse.calls == 0


def test_openverse_is_the_fallback_when_nothing_else_has_images():
    arasaac, openverse = FakeSource("arasaac"), FakeSource("openverse", results=5)
    pexels = FakeSource("pexels")

    found = _search(arasaac, openverse, pexels).find("idea", pos="noun", limit=5)

    assert {c.source for c in found} == {"openverse"}
    assert len(found) == 5
    assert (pexels.calls, arasaac.calls, openverse.calls) == (1, 1, 1)


def test_nouns_combine_pexels_and_arasaac_and_a_failing_source_is_skipped():
    pexels, arasaac = FakeSource("pexels", results=3), FakeSource("arasaac", results=5)
    openverse = FakeSource("openverse", results=5)

    found = _search(arasaac, openverse, pexels).find("apple", pos="noun", limit=5)
    assert [c.source for c in found] == ["pexels"] * 3 + ["arasaac"] * 2

    broken = FakeSource("arasaac", fail=True)
    fallback = _search(broken, openverse).find("happy", pos="adjective", limit=5)
    assert {c.source for c in fallback} == {"openverse"}
