"""Schemas del dashboard ("Quick access"): vista Today y vista Weekly pulse.

Cada seccion de dominio es None cuando el usuario no tiene el permiso de ese
dominio: asi el front distingue "no aplica" de "no hay datos" (que llega como
seccion con valores None o 0). Ver ulm-doc/plans/PLAN-DASHBOARD.md.
"""

from datetime import date, datetime

from pydantic import BaseModel

from app.schemas.calendar_event import CalendarEventRangeRead

# --- Today ---


class TodayWeightRead(BaseModel):
    last_recorded_on: date | None
    last_kg: float | None


class TodayEnglishRead(BaseModel):
    last_practice_at: datetime | None


class DashboardTodayRead(BaseModel):
    """`events`: festivos y fechas especiales (globales, para todos) mas los
    eventos personales si el usuario tiene `planning`."""

    date: date
    events: list[CalendarEventRangeRead]
    weight: TodayWeightRead | None
    english: TodayEnglishRead | None


# --- Weekly pulse ---


class PulseWeekRead(BaseModel):
    """Semana sabado-viernes. `elapsed_days` < 7 solo en la semana en curso."""

    first_day: date
    last_day: date
    in_progress: bool
    elapsed_days: int
    total_days: int


class PulseComparison(BaseModel):
    """Valor de la semana, de la anterior y promedio de las 4 anteriores.
    None = sin datos (ej. ninguna semana de checklist cubre esos dias)."""

    current: float | None
    previous: float | None
    average: float | None


class PulsePlanningRead(BaseModel):
    # Puntos logrados / posibles, en porcentaje (0-100).
    score_pct: PulseComparison


class PulseCategoryDeviation(BaseModel):
    label: str
    current: float
    average: float


class PulseFinancesRead(BaseModel):
    spent: PulseComparison
    # Categoria que mas subio frente a su promedio de 4 semanas; None si ninguna subio.
    top_deviation: PulseCategoryDeviation | None
    # Mes del ultimo dia de la semana (recortado a hoy): los ingresos son mensuales.
    month_first_day: date
    month_last_day: date
    month_income: float
    month_expenses: float
    # (ingresos - gastos) / ingresos, en porcentaje. None sin ingresos en el mes.
    savings_rate_pct: float | None


class PulseWeightRead(BaseModel):
    # Promedio semanal de los pesajes.
    average_kg: PulseComparison


class PulseEnglishRead(BaseModel):
    sessions: PulseComparison


class DashboardPulseRead(BaseModel):
    week: PulseWeekRead
    planning: PulsePlanningRead | None
    finances: PulseFinancesRead | None
    weight: PulseWeightRead | None
    english: PulseEnglishRead | None


class PulseInterpretationRequest(BaseModel):
    # Sin valor: la semana en curso.
    week_start: date | None = None


class PulseInterpretationRead(BaseModel):
    text: str
    model: str
