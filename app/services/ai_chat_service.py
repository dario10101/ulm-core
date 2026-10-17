"""Pregunta suelta al LLM: sin historial ni datos del usuario.

Es la base de las funcionalidades con IA; las siguientes (analisis sobre los
registros) reutilizan el mismo TextGenerator.
"""

from app.core.logging import get_logger
from app.integrations.openai_client import GeneratedText, TextGenerationError, TextGenerator
from app.services.ai_models import AI_MODELS, AiModel, find_model
from app.services.errors import AiNotConfiguredError, UnknownAiModelError

logger = get_logger(__name__)

INSTRUCTIONS = (
    "Eres el asistente de ULM, una app personal de registros (habitos, finanzas, "
    "salud). Responde en el idioma de la pregunta, de forma clara y concisa."
)


class AiChatService:
    def __init__(self, generator: TextGenerator | None, *, default_model: str) -> None:
        # None: no hay OPENAI_API_KEY configurada (ver deps.get_text_generator).
        self._generator = generator
        self._default_model = default_model

    def list_models(self) -> tuple[list[AiModel], str]:
        """Los del catalogo que la key tiene habilitados, y cual va preseleccionado."""
        generator = self._require_generator()
        try:
            available = generator.available_models()
            models = [model for model in AI_MODELS if model.id in available]
        except TextGenerationError as exc:
            # No se pudo preguntar: se ofrece el catalogo entero. Si un modelo no
            # esta habilitado, la pregunta falla con 502, igual que si OpenAI
            # estuviera caido.
            logger.warning("No se pudo listar los modelos de OpenAI: %s", exc)
            models = list(AI_MODELS)
        ids = [model.id for model in models]
        default = self._default_model if self._default_model in ids else (ids[0] if ids else "")
        return models, default

    def ask(self, *, user_id: int, question: str, model_id: str | None = None) -> GeneratedText:
        generator = self._require_generator()
        requested = model_id or self._default_model
        model = find_model(requested)
        if model is None:
            raise UnknownAiModelError(requested)
        result = generator.generate(
            model=model.id,
            instructions=INSTRUCTIONS,
            prompt=question,
            max_output_tokens=model.max_output_tokens,
            reasoning_effort=model.reasoning_effort,
        )
        # Solo metadatos: la pregunta puede tener informacion personal.
        logger.info(
            "Pregunta IA user_id=%s model=%s tokens_in=%s tokens_out=%s",
            user_id,
            result.model,
            result.input_tokens,
            result.output_tokens,
        )
        return result

    def _require_generator(self) -> TextGenerator:
        if self._generator is None:
            raise AiNotConfiguredError()
        return self._generator
