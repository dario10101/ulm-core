"""Esquemas Pydantic de entrada/salida para registros de peso."""

from datetime import date, datetime
from typing import Literal

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


WeightSummaryGroupBy = Literal["year", "month", "day"]


class WeightSummaryBucket(BaseModel):
    # "YYYY" (year), "YYYY-MM" (month) o "YYYY-MM-DD" (day).
    key: str
    average_kg: float
    count: int


class WeightSummaryRead(BaseModel):
    """Promedios por periodo para los graficos. Solo vienen los periodos con
    registros: rellenar huecos (meses/dias sin pesaje) es cosa del cliente."""

    buckets: list[WeightSummaryBucket]
    average_kg: float | None
    count: int
    # Años con algun registro (desc), para el selector de año del analisis.
    available_years: list[int]
