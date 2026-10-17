"""Esquemas Pydantic de las funcionalidades con IA."""

from pydantic import BaseModel, ConfigDict, Field


class AiAskRequest(BaseModel):
    # El tope de largo tambien es control de costo: los tokens de entrada se pagan.
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=2000)
    # Uno del catalogo (GET /ai/models). Sin el, el de OPENAI_MODEL.
    model: str | None = Field(default=None, max_length=100)


class AiAskResponse(BaseModel):
    answer: str
    model: str


class AiModelRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    label: str
    description: str
    input_usd_per_1m: float
    output_usd_per_1m: float


class AiModelsRead(BaseModel):
    models: list[AiModelRead]
    default: str
