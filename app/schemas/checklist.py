"""Esquemas Pydantic de entrada/salida del modulo de checklists."""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class Importance(str, Enum):
    HIGH = "HIGH"
    STANDARD = "STANDARD"


# Regla de negocio: HIGH suma 2 puntos, STANDARD suma 1. Unica fuente de verdad,
# tanto la lectura de tareas como los totales del template usan esta tabla.
POINTS_BY_IMPORTANCE: dict[Importance, int] = {
    Importance.HIGH: 2,
    Importance.STANDARD: 1,
}


# --- Categorias ---


class CategoryWrite(BaseModel):
    """Fila de categoria dentro del payload de guardado en bloque.

    id=None significa categoria nueva. El orden dentro de la lista define
    la prioridad (indice + 1), por eso no se envia como campo aparte.
    """

    id: int | None = None
    name: str = Field(min_length=1, max_length=120)


class CategoriesReplace(BaseModel):
    items: list[CategoryWrite]


class CategoryStatus(str, Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class CategoryRead(BaseModel):
    id: int
    name: str
    priority: int
    status: CategoryStatus


# --- Template tasks ---


class TemplateTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    importance: Importance
    category_id: int
    days: list[int] = Field(min_length=1, description="Dias 1-7 a los que aplica la tarea")
    detail: str | None = Field(default=None, max_length=2000)

    @field_validator("days")
    @classmethod
    def validate_days(cls, days: list[int]) -> list[int]:
        if any(day < 1 or day > 7 for day in days):
            raise ValueError("Los dias deben estar entre 1 y 7")
        if len(set(days)) != len(days):
            raise ValueError("Los dias no pueden repetirse")
        return sorted(set(days))


class TemplateTaskUpdate(BaseModel):
    """Reemplazo de una tarea para un unico dia (ver estrategia de split en el service)."""

    name: str = Field(min_length=1, max_length=200)
    importance: Importance
    category_id: int
    detail: str | None = Field(default=None, max_length=2000)


class TemplateTaskRead(BaseModel):
    id: int
    name: str
    importance: Importance
    points: int
    category_id: int
    days: list[int]
    detail: str | None


# --- Semanas y tareas concretas ---


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETE = "COMPLETE"
    FAILED = "FAILED"


class WeekCreate(BaseModel):
    first_day: date
    last_day: date

    @field_validator("last_day")
    @classmethod
    def validate_range(cls, last_day: date, info: ValidationInfo) -> date:
        first_day = info.data.get("first_day")
        if first_day is not None and not (0 <= (last_day - first_day).days <= 6):
            raise ValueError("La semana debe cubrir entre 1 y 7 dias (last_day entre first_day y first_day+6)")
        return last_day


class WeekRead(BaseModel):
    id: int
    first_day: date
    last_day: date
    closed: bool
    closed_date: datetime | None
    score: int | None


class WeekRangeRead(BaseModel):
    """Limites minimos para crear la proxima semana (ver WeekService.get_next_range)."""

    min_first_day: date
    min_last_day: date


class TaskStatusUpdate(BaseModel):
    status: TaskStatus


class TaskCreate(BaseModel):
    """Tarea circunstancial agregada directamente a una semana, sin pasar por
    (ni modificar) el template."""

    name: str = Field(min_length=1, max_length=200)
    importance: Importance
    category_id: int
    day_of_week: int = Field(ge=1, le=7)
    detail: str | None = Field(default=None, max_length=2000)


class TaskUpdate(BaseModel):
    """Edicion de una tarea de semana ya existente (modo Edit del checklist).
    El dia y la semana no cambian, solo nombre/importancia/categoria/detalle."""

    name: str = Field(min_length=1, max_length=200)
    importance: Importance
    category_id: int
    detail: str | None = Field(default=None, max_length=2000)


class TaskRead(BaseModel):
    id: int
    name: str
    importance: Importance
    points: int
    category_id: int
    day_of_week: int
    status: TaskStatus
    last_modified_date: datetime
    detail: str | None


# --- Analytics (tendencias de semanas cerradas) ---


class AnalyticsCategory(BaseModel):
    """Una serie del grafico. category_id=None es el bucket agregado "Others"
    (categorias de menor puntaje agrupadas, ver ChecklistAnalyticsService)."""

    category_id: int | None
    name: str


class WeeklyAnalyticsPoint(BaseModel):
    week_id: int
    first_day: date
    last_day: date
    total_score: int
    # Alineado 1:1 con `categories` de WeeklyAnalyticsRead.
    scores: list[int]


class WeeklyAnalyticsRead(BaseModel):
    year: int
    categories: list[AnalyticsCategory]
    weeks: list[WeeklyAnalyticsPoint]


class MonthlyAnalyticsPoint(BaseModel):
    month: int = Field(ge=1, le=12)
    total_score: int
    # Alineado 1:1 con `categories` de MonthlyAnalyticsRead.
    scores: list[int]


class MonthlyAnalyticsRead(BaseModel):
    year: int
    categories: list[AnalyticsCategory]
    months: list[MonthlyAnalyticsPoint]
