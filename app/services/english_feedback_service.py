"""Feedback de una practica, solo si el usuario lo pide (ENGLISH-TEACHER-PLAN.md, 7.2).

Idempotente: si ya existe, se devuelve el guardado sin llamar al LLM. La
misma llamada reescribe la memoria del usuario (eng_user_memory).

Una respuesta mal formada despues de pagar NO levanta un error: el request se
revertiria y se perderia el registro del consumo. El service devuelve el
fallo como resultado y la ruta responde 502 sin excepcion (se commitea).
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from pydantic import ValidationError as PydanticValidationError

from app.core.logging import get_logger
from app.db.models.english import EngPracticeFeedback, EngUserMemory
from app.integrations.openai_client import TextGenerator
from app.repositories.english_practice_repository import EnglishPracticeRepository
from app.services.ai_models import AiModel
from app.services.ai_usage_service import AiUsageRecorder
from app.services.english_feedback import (
    MEMORY_MAX_CHARS,
    FeedbackResponse,
    build_instructions,
    build_prompt,
    response_schema,
)
from app.services.english_levels import EnglishLevel
from app.services.errors import AiNotConfiguredError, EnglishPracticeNotFoundError

logger = get_logger(__name__)

USAGE_FEATURE = "english.feedback"


@dataclass(frozen=True)
class FeedbackOutcome:
    feedback: FeedbackResponse | None
    model: str
    # True si la respuesta del LLM no se pudo usar (ya se pago).
    invalid_response: bool = False


class EnglishFeedbackService:
    def __init__(
        self,
        repository: EnglishPracticeRepository,
        generator: TextGenerator | None,
        usage: AiUsageRecorder,
        *,
        model: AiModel,
        max_output_tokens: int,
    ) -> None:
        self._repository = repository
        self._generator = generator
        self._usage = usage
        self._model = model
        self._max_output_tokens = max_output_tokens

    def get_or_create(self, user_id: int, practice_id: int) -> FeedbackOutcome:
        practice = self._repository.get_practice(practice_id, user_id=user_id)
        if practice is None:
            raise EnglishPracticeNotFoundError(practice_id)
        saved = self._repository.get_feedback(practice_id)
        if saved is not None:
            return FeedbackOutcome(FeedbackResponse.model_validate(saved.feedback), saved.model)
        if self._generator is None:
            raise AiNotConfiguredError()

        word = self._repository.get_word(practice.word_id)
        content = self._repository.get_content(practice.content_id)
        assert word is not None and content is not None  # FKs de la practica
        memory = self._repository.get_memory(user_id=user_id)

        result = self._generator.generate(
            model=self._model.id,
            instructions=build_instructions(EnglishLevel(practice.level)),
            prompt=build_prompt(practice, word, content, memory.summary if memory else None),
            max_output_tokens=self._max_output_tokens,
            reasoning_effort=self._model.reasoning_effort,
            json_schema=response_schema(),
        )
        # Desde aca ya se pago: nada debe levantar un error.
        self._usage.record_text(user_id=user_id, feature=USAGE_FEATURE, result=result)
        try:
            feedback = FeedbackResponse.model_validate_json(result.text)
        except PydanticValidationError as exc:
            logger.warning("Feedback de ingles con formato invalido: %s", exc)
            return FeedbackOutcome(None, result.model, invalid_response=True)

        self._repository.add_feedback(
            EngPracticeFeedback(
                practice_id=practice.id,
                feedback=feedback.model_dump(),
                model=result.model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
            )
        )
        summary = feedback.memory_update.strip()[:MEMORY_MAX_CHARS]
        if summary:
            if memory is None:
                self._repository.add_memory(EngUserMemory(user_id=user_id, summary=summary))
            else:
                memory.summary = summary
                memory.updated_at = datetime.now(UTC)
        self._repository.flush()
        return FeedbackOutcome(feedback, result.model)
