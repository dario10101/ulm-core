"""Registro del consumo de cada llamada pagada a un proveedor de IA.

Es el punto unico de paso (*chokepoint*) para el futuro control de creditos
(ENGLISH-TEACHER-PLAN.md, D7/D23): quien llama a OpenAI registra aca, y el dia
que haya saldos, el chequeo "sin creditos -> no llamar" se agrega en un solo
lugar. El costo es una estimacion con los precios informativos del catalogo.

El evento va en la transaccion del request: quien lo use no debe levantar un
error despues de una llamada pagada (se perderia el registro con el rollback).
"""

from app.db.models.ai_usage import AiUsageEvent
from app.integrations.openai_client import GeneratedText
from app.repositories.ai_usage_repository import AiUsageRepository
from app.services.ai_models import AI_MODELS, find_model


class AiUsageRecorder:
    def __init__(self, repository: AiUsageRepository) -> None:
        self._repository = repository

    def record_text(self, *, user_id: int, feature: str, result: GeneratedText) -> None:
        # result.model trae la version exacta (ej. "gpt-6-luna-2026-09-01"); el
        # precio se busca por el id del catalogo que la contiene.
        model = find_model(result.model) or next(
            (m for m in AI_MODELS if result.model.startswith(m.id)), None
        )
        cost = 0.0
        if model is not None:
            cost = (
                result.input_tokens * model.input_usd_per_1m
                + result.output_tokens * model.output_usd_per_1m
            ) / 1_000_000
        self._repository.add(
            AiUsageEvent(
                user_id=user_id,
                feature=feature,
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                estimated_cost_usd=cost,
            )
        )

    def record_audio(
        self, *, user_id: int, feature: str, model: str, seconds: float, usd_per_minute: float
    ) -> None:
        self._repository.add(
            AiUsageEvent(
                user_id=user_id,
                feature=feature,
                model=model,
                audio_seconds=seconds,
                estimated_cost_usd=seconds / 60 * usd_per_minute,
            )
        )
