"""Cliente de generacion de texto de OpenAI (Responses API).

AiChatService depende del Protocol y no de esta clase: los tests le pasan un
generador falso y nunca llaman a OpenAI. Los errores del SDK se traducen a
TextGenerationError, asi ninguna capa de arriba importa `openai`.

`store=False`: la Responses API guarda por defecto cada respuesta en OpenAI
(para encadenarlas con previous_response_id). Este modulo es sin contexto, asi
que no hay nada que encadenar y no tiene sentido dejar las preguntas alla.
"""

from dataclasses import dataclass
from typing import Any, Protocol

import openai


class TextGenerationError(Exception):
    """El proveedor fallo: key invalida, sin saldo, rate limit, timeout, caido."""


@dataclass(frozen=True)
class GeneratedText:
    text: str
    model: str
    input_tokens: int
    output_tokens: int


class TextGenerator(Protocol):
    def generate(
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        max_output_tokens: int,
        reasoning_effort: str | None,
        json_schema: dict[str, Any] | None = None,
    ) -> GeneratedText:
        """Con `json_schema`, la respuesta es un JSON que cumple ese esquema
        (salida estructurada, modo estricto): el que llama la parsea."""
        ...

    def available_models(self) -> frozenset[str]:
        """IDs de los modelos que la key tiene habilitados."""
        ...


class OpenAiTextGenerator:
    def __init__(self, *, api_key: str, timeout_seconds: float) -> None:
        # max_retries=1: el SDK reintenta 429/5xx con backoff; con el default (2)
        # un request colgado puede tardar 3 veces el timeout.
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout_seconds, max_retries=1)
        self._available: frozenset[str] | None = None

    def generate(
        self,
        *,
        model: str,
        instructions: str,
        prompt: str,
        max_output_tokens: int,
        reasoning_effort: str | None,
        json_schema: dict[str, Any] | None = None,
    ) -> GeneratedText:
        # Un modelo no razonador rechaza el parametro `reasoning`: va solo si aplica.
        extra: dict[str, Any] = (
            {"reasoning": {"effort": reasoning_effort}} if reasoning_effort else {}
        )
        if json_schema is not None:
            extra["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": json_schema.get("title", "response"),
                    "schema": json_schema,
                    "strict": True,
                }
            }
        try:
            response = self._client.responses.create(
                model=model,
                instructions=instructions,
                input=prompt,
                max_output_tokens=max_output_tokens,
                store=False,
                **extra,
            )
        except openai.OpenAIError as exc:
            raise TextGenerationError(f"{type(exc).__name__}: {exc}") from exc

        text = response.output_text
        if not text:
            # Pasa si el tope de tokens se gasto antes de escribir nada (ej. un
            # modelo de razonamiento) o si el contenido fue filtrado.
            raise TextGenerationError(f"Respuesta vacia (status={response.status})")
        usage = response.usage
        return GeneratedText(
            text=text,
            model=response.model,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
        )

    def available_models(self) -> frozenset[str]:
        # Una vez por proceso: la lista cambia cada varios meses y la llamada
        # (gratis) tarda. Un modelo recien habilitado aparece al reiniciar la API.
        if self._available is None:
            try:
                self._available = frozenset(model.id for model in self._client.models.list())
            except openai.OpenAIError as exc:
                raise TextGenerationError(f"{type(exc).__name__}: {exc}") from exc
        return self._available
