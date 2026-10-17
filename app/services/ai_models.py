"""Catalogo de modelos de OpenAI que se pueden elegir en "AI features".

Es una lista cerrada a proposito: el front solo puede pedir uno de estos, asi
nadie manda un modelo `-pro` (30-180 USD por millon de tokens) desde la
consola del navegador. GET /ai/models lo cruza con los que la key tiene
habilitados (ver AiChatService.list_models).

Precios por millon de tokens (entrada/salida), tier estandar, tomados de
developers.openai.com/api/docs/pricing el 2026-10-07. Son informativos (la UI
los muestra para elegir): OpenAI cobra lo que diga su pagina, no esto.

`reasoning_effort`: None es un modelo no razonador (no se manda el parametro).
En uno razonador los tokens de razonamiento salen del mismo tope de
`max_output_tokens`; con un tope chico puede gastarlo entero pensando y no
escribir nada, por eso los que no admiten "none" tienen un tope mayor.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class AiModel:
    id: str
    label: str
    description: str
    input_usd_per_1m: float
    output_usd_per_1m: float
    reasoning_effort: str | None
    max_output_tokens: int


AI_MODELS: tuple[AiModel, ...] = (
    AiModel(
        id="gpt-6-luna",
        label="GPT-6 Luna",
        description="Newest and cheapest. Fast answers, no reasoning.",
        input_usd_per_1m=0.10,
        output_usd_per_1m=0.50,
        reasoning_effort="none",
        max_output_tokens=800,
    ),
    AiModel(
        id="gpt-6.1-sol",
        label="GPT-6.1 Sol",
        description="Balanced intelligence and cost. Light reasoning.",
        input_usd_per_1m=2.00,
        output_usd_per_1m=10.00,
        reasoning_effort="low",
        max_output_tokens=2000,
    ),
    AiModel(
        id="gpt-6-astra",
        label="GPT-6 Astra",
        description="Most capable and most expensive. Light reasoning.",
        input_usd_per_1m=10.00,
        output_usd_per_1m=50.00,
        reasoning_effort="low",
        max_output_tokens=2000,
    ),
    AiModel(
        id="gpt-4.1-mini",
        label="GPT-4.1 mini",
        description="Previous generation, no reasoning.",
        input_usd_per_1m=0.40,
        output_usd_per_1m=1.60,
        reasoning_effort=None,
        max_output_tokens=800,
    ),
    AiModel(
        id="gpt-4.1-nano",
        label="GPT-4.1 nano",
        description="Previous generation, smallest. No reasoning.",
        input_usd_per_1m=0.10,
        output_usd_per_1m=0.40,
        reasoning_effort=None,
        max_output_tokens=800,
    ),
)

_BY_ID = {model.id: model for model in AI_MODELS}


def find_model(model_id: str) -> AiModel | None:
    return _BY_ID.get(model_id)
