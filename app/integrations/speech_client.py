"""Transcripcion de voz con OpenAI (ENGLISH-TEACHER-PLAN.md, C1 y 7.3).

Ningun ASR transcribe "tal cual suena": todos eligen la palabra mas probable.
Lo que se puede hacer para no esconder los errores del usuario:
- Prompt solo con muletillas: el truco conocido de Whisper para que conserve
  "umm", repeticiones y titubeos en vez de limpiarlos.
- NUNCA pasar el texto esperado como prompt: sesgaria la transcripcion hacia
  el texto correcto y ocultaria justo lo que se quiere detectar.

El service depende del Protocol; los tests usan un transcriptor falso.
"""

from dataclasses import dataclass
from typing import Protocol

import openai

# Muletillas en el prompt: Whisper tiende a imitar el estilo del prompt.
VERBATIM_PROMPT = "Umm, let me think, like, hmm... I, I mean... uh, you know, so, er..."

EXTENSIONS = {
    "audio/webm": "webm",
    "audio/ogg": "ogg",
    "audio/mp4": "mp4",
    "audio/mpeg": "mp3",
    "audio/wav": "wav",
    "audio/x-wav": "wav",
    "audio/m4a": "m4a",
    "audio/x-m4a": "m4a",
}


class TranscriptionError(Exception):
    """El proveedor fallo (key invalida, sin saldo, audio ilegible, caido)."""


@dataclass(frozen=True)
class Transcription:
    text: str
    # Duracion segun el proveedor; None si el modelo no la informa.
    duration_seconds: float | None


class SpeechTranscriber(Protocol):
    def transcribe(self, *, audio: bytes, content_type: str, model: str) -> Transcription: ...


def extension_for(content_type: str) -> str | None:
    """Extension que OpenAI usa para reconocer el formato ("audio/webm;codecs=opus" -> webm)."""
    return EXTENSIONS.get(content_type.split(";")[0].strip().lower())


class OpenAiSpeechTranscriber:
    def __init__(self, *, api_key: str, timeout_seconds: float) -> None:
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=1)

    def transcribe(self, *, audio: bytes, content_type: str, model: str) -> Transcription:
        extension = extension_for(content_type) or "webm"
        # verbose_json trae la duracion, pero solo lo aceptan los whisper; los
        # gpt-4o-*-transcribe solo devuelven json.
        verbose = model.startswith("whisper")
        try:
            result = self._client.audio.transcriptions.create(
                model=model,
                file=(f"speech.{extension}", audio, content_type.split(";")[0]),
                language="en",
                prompt=VERBATIM_PROMPT,
                response_format="verbose_json" if verbose else "json",
            )
        except openai.OpenAIError as exc:
            raise TranscriptionError(f"{type(exc).__name__}: {exc}") from exc
        duration = getattr(result, "duration", None)
        return Transcription(
            text=(result.text or "").strip(),
            duration_seconds=float(duration) if duration is not None else None,
        )
