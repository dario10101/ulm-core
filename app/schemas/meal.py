"""Esquemas Pydantic de entrada/salida para registros de comida (meals)."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class MealType(str, Enum):
    BREAKFAST = "BREAKFAST"
    MID_MORNING_SNACK = "MID_MORNING_SNACK"
    LUNCH = "LUNCH"
    MID_AFTERNOON_SNACK = "MID_AFTERNOON_SNACK"
    DINNER = "DINNER"
    LATE_NIGHT_SNACK = "LATE_NIGHT_SNACK"


def _reject_aware(value: datetime) -> datetime:
    """La API recibe hora de pared del usuario, sin offset (ej.
    "2026-09-26T13:30:00"): es el backend quien le adjunta la zona del
    usuario y la convierte a UTC para guardarla (mismo contrato que
    cld_tasks, ver app/services/cld_task_sync.py)."""
    if value.tzinfo is not None:
        raise ValueError("Enviar la fecha en hora local sin zona horaria (ej. 2026-09-26T13:30:00)")
    return value


class MealComponentIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    # Porcentaje final del plato que representa este componente. El reparto
    # entre componentes (que sumen 100) es responsabilidad del frontend; el
    # backend no lo revalida para no fallar por un redondeo de +-1.
    percent: int = Field(ge=0, le=100)


class MealCreate(BaseModel):
    recorded_on: datetime
    meal_type: MealType
    # Porcentaje de una porcion completa que representa el plato (0-100).
    meal_size: int = Field(ge=0, le=100)
    components: list[MealComponentIn] = Field(default_factory=list)
    drink: str | None = Field(default=None, max_length=60)
    note: str | None = Field(default=None, max_length=2000)

    _no_tz = field_validator("recorded_on")(_reject_aware)

    @model_validator(mode="after")
    def validate_components_or_drink(self) -> "MealCreate":
        has_components = any(c.name.strip() for c in self.components)
        has_drink = bool(self.drink and self.drink.strip())
        if not has_components and not has_drink:
            raise ValueError("Se requiere al menos un componente del plato o una bebida")
        return self


class MealUpdate(MealCreate):
    """Mismos campos que la creacion: es un reemplazo completo del registro."""


class MealRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    recorded_on: datetime
    meal_type: MealType
    meal_size: int
    meal_content: str | None
    drink: str | None
    note: str | None
    created_at: datetime
    updated_at: datetime | None


class MealPage(BaseModel):
    items: list[MealRead]
    total: int
    page: int
    page_size: int
    total_pages: int
