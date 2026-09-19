"""Esquemas Pydantic de entrada/salida para registros de peso."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class WeightCreate(BaseModel):
    weight_kg: float = Field(gt=0, description="Peso en kilogramos")
    recorded_on: date
    note: str | None = Field(default=None, max_length=500)


class WeightUpdate(WeightCreate):
    """Mismos campos que la creacion: es un reemplazo completo del registro."""


class WeightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    weight_kg: float
    recorded_on: date
    note: str | None
    created_at: datetime
    updated_at: datetime | None


class WeightPage(BaseModel):
    items: list[WeightRead]
    total: int
    page: int
    page_size: int
    total_pages: int
