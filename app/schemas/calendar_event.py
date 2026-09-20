"""Esquemas Pydantic de eventos de calendario (festivos y eventos generales
de cld_events, mas los personales de cld_user_events), vistos como
marcadores de inicio/fin dentro de un rango (ver CalendarEventService)."""

from datetime import date
from enum import Enum

from pydantic import BaseModel


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
