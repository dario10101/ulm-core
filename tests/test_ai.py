"""Pruebas de las funcionalidades con IA.

Nunca llaman a OpenAI: se reemplaza `get_text_generator` por un generador
falso (o por None, que es lo que devuelve sin OPENAI_API_KEY).
"""

import pytest

from app.api.deps import get_text_generator
from app.integrations.openai_client import GeneratedText, TextGenerationError
from app.main import app
from app.services.ai_chat_service import INSTRUCTIONS
from app.services.ai_models import AI_MODELS
from tests.conftest import client

ASK_URL = "/api/v1/ai/ask"
MODELS_URL = "/api/v1/ai/models"
CATALOG_IDS = [model.id for model in AI_MODELS]


class FakeGenerator:
    def __init__(self, *, fail: bool = False, available: frozenset[str] | None = None) -> None:
        self.fail = fail
        # None: la key tiene todo el catalogo habilitado.
        self.available = frozenset(CATALOG_IDS) if available is None else available
        self.fail_listing = False
        self.calls: list[dict] = []

    def generate(self, **kwargs) -> GeneratedText:
        self.calls.append(kwargs)
        if self.fail:
            raise TextGenerationError("RateLimitError: sin saldo")
        return GeneratedText(
            text=f"eco: {kwargs['prompt']}", model=kwargs["model"], input_tokens=5, output_tokens=3
        )

    def available_models(self) -> frozenset[str]:
        if self.fail_listing:
            raise TextGenerationError("APIConnectionError")
        return self.available


@pytest.fixture
def generator() -> FakeGenerator:
    fake = FakeGenerator()
    app.dependency_overrides[get_text_generator] = lambda: fake
    return fake


# --- Preguntar ---


def test_ask_uses_the_default_model(generator):
    response = client.post(ASK_URL, json={"question": "  hola  "})

    assert response.status_code == 200
    assert response.json() == {"answer": "eco: hola", "model": "gpt-6-luna"}
    # La pregunta llega recortada, con las instrucciones y la config del modelo.
    assert generator.calls == [
        {
            "model": "gpt-6-luna",
            "instructions": INSTRUCTIONS,
            "prompt": "hola",
            "max_output_tokens": 800,
            "reasoning_effort": "none",
        }
    ]


def test_ask_with_a_chosen_model_sends_its_settings(generator):
    response = client.post(ASK_URL, json={"question": "hola", "model": "gpt-4.1-mini"})

    assert response.status_code == 200
    assert response.json()["model"] == "gpt-4.1-mini"
    # No razonador: no se manda reasoning_effort.
    assert generator.calls[0]["reasoning_effort"] is None


def test_ask_rejects_a_model_outside_the_catalog(generator):
    response = client.post(ASK_URL, json={"question": "hola", "model": "gpt-5.5-pro"})

    assert response.status_code == 422
    assert generator.calls == []


@pytest.mark.parametrize("question", ["", "   ", "x" * 2001])
def test_ask_rejects_empty_or_too_long_questions(generator, question):
    response = client.post(ASK_URL, json={"question": question})

    assert response.status_code == 422
    assert generator.calls == []


def test_ask_without_api_key_returns_503():
    app.dependency_overrides[get_text_generator] = lambda: None

    response = client.post(ASK_URL, json={"question": "hola"})

    assert response.status_code == 503


def test_ask_hides_provider_errors_behind_502():
    app.dependency_overrides[get_text_generator] = lambda: FakeGenerator(fail=True)

    response = client.post(ASK_URL, json={"question": "hola"})

    assert response.status_code == 502
    assert "saldo" not in response.json()["detail"]


# --- Modelos ---


def test_models_lists_the_catalog_in_order_with_the_default(generator):
    response = client.get(MODELS_URL)

    assert response.status_code == 200
    body = response.json()
    assert [model["id"] for model in body["models"]] == CATALOG_IDS
    assert body["default"] == "gpt-6-luna"
    assert set(body["models"][0]) == {
        "id",
        "label",
        "description",
        "input_usd_per_1m",
        "output_usd_per_1m",
    }


def test_models_hides_the_ones_the_key_cannot_use():
    fake = FakeGenerator(available=frozenset({"gpt-4.1-mini", "gpt-4.1-nano", "whisper-1"}))
    app.dependency_overrides[get_text_generator] = lambda: fake

    body = client.get(MODELS_URL).json()

    assert [model["id"] for model in body["models"]] == ["gpt-4.1-mini", "gpt-4.1-nano"]
    # El default configurado no esta habilitado: se preselecciona el primero.
    assert body["default"] == "gpt-4.1-mini"


def test_models_falls_back_to_the_catalog_if_listing_fails(generator):
    generator.fail_listing = True

    body = client.get(MODELS_URL).json()

    assert [model["id"] for model in body["models"]] == CATALOG_IDS


def test_models_without_api_key_returns_503():
    app.dependency_overrides[get_text_generator] = lambda: None

    assert client.get(MODELS_URL).status_code == 503
