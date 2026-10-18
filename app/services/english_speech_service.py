"""Speaking de la practica: transcribir la voz y comparar la lectura (ENGLISH-TEACHER-PLAN.md, 7.3).

No necesita una practica guardada (D8): recibe el `content_id` para saber el
texto esperado de la fase de lectura. Cada transcripcion se registra en
ai_usage_events en el momento, aunque despues el usuario abandone la practica.
"""

from dataclasses import dataclass

from app.integrations.speech_client import SpeechTranscriber, extension_for
from app.repositories.english_practice_repository import EnglishPracticeRepository
from app.services.ai_usage_service import AiUsageRecorder
from app.services.english_levels import EnglishLevel, level_config
from app.services.english_reading_diff import ReadingDiff, compare_reading
from app.services.errors import (
    AiNotConfiguredError,
    EnglishAudioInvalidError,
    EnglishContentNotFoundError,
)

USAGE_FEATURE = "english.transcription"
# Tope de la grabacion de lectura (segundos): un texto de 6 frases se lee en
# menos de un minuto incluso despacio.
READING_MAX_SECONDS = 120
# Margen sobre el tope del nivel: el cronometro del navegador no es exacto.
DURATION_MARGIN_SECONDS = 10


@dataclass(frozen=True)
class SpeechResult:
    transcript: str
    duration_seconds: float
    diff: ReadingDiff | None


class EnglishSpeechService:
    def __init__(
        self,
        repository: EnglishPracticeRepository,
        transcriber: SpeechTranscriber | None,
        usage: AiUsageRecorder,
        *,
        model: str,
        usd_per_minute: float,
        max_bytes: int,
    ) -> None:
        self._repository = repository
        # None: no hay OPENAI_API_KEY.
        self._transcriber = transcriber
        self._usage = usage
        self._model = model
        self._usd_per_minute = usd_per_minute
        self._max_bytes = max_bytes

    def transcribe(
        self,
        *,
        user_id: int,
        content_id: int,
        phase: str,
        audio: bytes,
        content_type: str,
        client_seconds: float,
    ) -> SpeechResult:
        if self._transcriber is None:
            raise AiNotConfiguredError()
        content = self._repository.get_content(content_id)
        if content is None:
            raise EnglishContentNotFoundError(content_id)
        # Validar antes de llamar al proveedor: lo que se rechaza aca no se paga.
        if not audio:
            raise EnglishAudioInvalidError("El audio esta vacio")
        if len(audio) > self._max_bytes:
            raise EnglishAudioInvalidError("El audio supera el tamaño maximo")
        if extension_for(content_type) is None:
            raise EnglishAudioInvalidError(f"Formato de audio no soportado: {content_type}")
        limit = (
            READING_MAX_SECONDS
            if phase == "reading"
            else level_config(EnglishLevel(content.level)).free_speaking_seconds
        )
        if client_seconds > limit + DURATION_MARGIN_SECONDS:
            raise EnglishAudioInvalidError(f"La grabacion supera el tope de {limit} segundos")

        result = self._transcriber.transcribe(
            audio=audio, content_type=content_type, model=self._model
        )
        seconds = result.duration_seconds or client_seconds
        # Ya se pago: registrar y no levantar errores despues.
        self._usage.record_audio(
            user_id=user_id,
            feature=USAGE_FEATURE,
            model=self._model,
            seconds=seconds,
            usd_per_minute=self._usd_per_minute,
        )
        diff = compare_reading(content.reading_text, result.text) if phase == "reading" else None
        return SpeechResult(transcript=result.text, duration_seconds=seconds, diff=diff)
