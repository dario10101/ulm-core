"""Esquemas Pydantic de eventos de calendario (festivos y eventos generales
de cld_events, mas los personales de cld_user_events), vistos como
marcadores de inicio/fin dentro de un rango (ver CalendarEventService)."""

from datetime import date
from enum import Enum
from typing import Annotated, Self

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


class MarkerType(str, Enum):
    START = "start"
    END = "end"
    SINGLE = "single"


class MarkerSource(str, Enum):
    # De cld_events: festivos y otros eventos generales (no ligados a un
    # usuario). El "code" del evento (ej. "HOLIDAY") va en `code`.
    EVENT = "event"
    # De cld_user_events: rangos personales del usuario (vacaciones, viajes).
    USER_EVENT = "user_event"


class CalendarEventMarkerRead(BaseModel):
    id: int
    name: str
    detail: str | None
    marker_date: date
    marker_type: MarkerType
    source: MarkerSource
    code: str | None


class CalendarEventRangeRead(BaseModel):
    """Rango completo (sin recortar a inicio/fin) de un evento que se
    solapa con el rango pedido. A diferencia de CalendarEventMarkerRead,
    sirve para saber TODOS los dias que un evento cubre (ej. para pintar
    el fondo de cada celda de la vista mensual), no solo donde empieza o
    termina."""

    id: int
    name: str
    detail: str | None
    code: str | None
    source: MarkerSource
    first_day: date
    last_day: date
    # Solo los eventos personales tienen categoria; el front la necesita para
    # prellenar la edicion y para filtrar la vista diaria por categoria.
    category_id: int | None = None


# --- Eventos personales del usuario (cld_user_events) ---


def _normalize_code(value: str) -> str:
    """El tipo se guarda siempre en mayusculas y sin espacios sobrantes, asi
    "  travel " y "TRAVEL" son el mismo tipo y no aparecen dos veces en el
    selector."""
    return " ".join(value.split()).upper()


EventCode = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=30),
    AfterValidator(_normalize_code),
]


class CldUserEventWrite(BaseModel):
    category_id: int
    code: EventCode
    first_day: date
    last_day: date
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    detail: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _range_is_ordered(self) -> Self:
        if self.last_day < self.first_day:
            raise ValueError("last_day no puede ser anterior a first_day")
        return self


class CldUserEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    category_id: int
    code: str
    first_day: date
    last_day: date
    name: str
    detail: str | None


# --- Administracion de eventos generales (Settings -> Calendar events) ---


class CldEventCode(str, Enum):
    """Tipos de evento general que administra el admin."""

    HOLIDAY = "HOLIDAY"
    # Fechas especiales que no son festivo (Dia de la Madre, Halloween...).
    SPECIAL_DATE = "SPECIAL_DATE"


class CldEventWrite(BaseModel):
    code: CldEventCode
    first_day: date
    last_day: date
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
    detail: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _range_is_ordered(self) -> Self:
        if self.last_day < self.first_day:
            raise ValueError("last_day no puede ser anterior a first_day")
        return self


class CldEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    first_day: date
    last_day: date
    name: str
    detail: str | None


class OfficialHolidayRead(BaseModel):
    """Festivo que calcula la libreria. `event_id` es el HOLIDAY de
    cld_events que cae ese dia, o None si el admin no lo tiene cargado."""

    day: date
    name: str
    event_id: int | None


class CalendarYearRead(BaseModel):
    year: int
    country: str
    events: list[CldEventRead]
    official_holidays: list[OfficialHolidayRead]


class ImportHolidaysRequest(BaseModel):
    year: int = Field(ge=1900, le=2200)
