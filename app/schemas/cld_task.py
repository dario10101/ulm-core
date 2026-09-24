"""Esquemas Pydantic de entrada/salida de tareas de calendario (cld_tasks)."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.checklist import Importance


class RepeatMode(str, Enum):
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"
    YEARLY = "YEARLY"


def _reject_aware(value: datetime | None) -> datetime | None:
    """La API recibe hora de pared del usuario, sin offset (ej.
    "2026-09-15T19:30:00"): es el backend quien le adjunta la zona del
    usuario y la convierte a UTC para guardarla. Un datetime con offset
    significa que el cliente ya convirtio por su cuenta —posiblemente con la
    zona del navegador, que no tiene por que ser la del usuario—, asi que se
    rechaza en vez de aceptarlo en silencio."""
    if value is not None and value.tzinfo is not None:
        raise ValueError("Enviar la fecha en hora local sin zona horaria (ej. 2026-09-15T19:30:00)")
    return value


def _validate_same_day_duration(anchor: datetime | None, duration_minutes: int) -> None:
    """La hora final (anchor + duration_minutes) nunca puede cruzar la
    medianoche del dia de anchor. Se evalua en hora local del usuario, que
    es la que este ve en el formulario."""
    if anchor is None:
        return
    start_minutes = anchor.hour * 60 + anchor.minute
    if start_minutes + duration_minutes > 24 * 60:
        raise ValueError("duration_minutes haria que la tarea terminara al dia siguiente")


class CldTaskCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    importance: Importance
    category_id: int
    notify: bool = True
    repeat_mode: RepeatMode | None = None
    # Exactamente uno de los dos debe venir, segun haya o no repeat_mode
    # (ver validate_dates): scheduled_date para una tarea puntual, repeat_date
    # como ancla (dia/mes/hora) para una tarea recurrente.
    scheduled_date: datetime | None = None
    repeat_date: datetime | None = None
    # Minutos desde la hora de inicio hasta la hora final. Nunca puede cruzar
    # la medianoche del dia de inicio (ver _validate_same_day_duration).
    duration_minutes: int = Field(default=60, ge=1, le=1439)
    add_to_checklist: bool = False
    detail: str | None = Field(default=None, max_length=2000)

    _no_tz = field_validator("scheduled_date", "repeat_date")(_reject_aware)

    @model_validator(mode="after")
    def validate_dates(self) -> "CldTaskCreate":
        if self.repeat_mode is None:
            if self.scheduled_date is None:
                raise ValueError("scheduled_date es requerido cuando la tarea no se repite")
            if self.repeat_date is not None:
                raise ValueError("repeat_date no aplica a una tarea que no se repite")
        else:
            if self.repeat_date is None:
                raise ValueError("repeat_date es requerido para una tarea con repeticion")
            if self.scheduled_date is not None:
                raise ValueError("scheduled_date no aplica a una tarea con repeticion")
        _validate_same_day_duration(self.scheduled_date or self.repeat_date, self.duration_minutes)
        return self


class CldTaskUpdate(BaseModel):
    """Edicion de una tarea de calendario. No incluye repeat_mode ni
    add_to_checklist a proposito: no son editables desde este formulario."""

    name: str = Field(min_length=1, max_length=200)
    importance: Importance
    category_id: int
    notify: bool
    # Igual que en la creacion: exactamente uno de los dos, segun si la tarea
    # (ya existente) repite o no. Se valida contra el repeat_mode guardado.
    scheduled_date: datetime | None = None
    repeat_date: datetime | None = None
    duration_minutes: int = Field(ge=1, le=1439)
    detail: str | None = Field(default=None, max_length=2000)

    _no_tz = field_validator("scheduled_date", "repeat_date")(_reject_aware)

    @model_validator(mode="after")
    def validate_duration(self) -> "CldTaskUpdate":
        _validate_same_day_duration(self.scheduled_date or self.repeat_date, self.duration_minutes)
        return self


class CldTaskRead(BaseModel):
    id: int
    name: str
    importance: Importance
    category_id: int
    notify: bool
    repeat_mode: RepeatMode | None
    scheduled_date: datetime | None
    repeat_date: datetime | None
    duration_minutes: int
    add_to_checklist: bool
    detail: str | None
    last_modified_date: datetime


class CldTaskOccurrenceRead(BaseModel):
    """Una ocurrencia concreta de una tarea de calendario en un dia puntual
    (ver CldTaskService.list_for_day). Incluye el ancla cruda (scheduled_date
    o repeat_date) ademas de occurrence_at: al editar, el formulario debe
    partir del ancla real de la serie, no de esta ocurrencia puntual (que en
    modo MONTHLY puede venir con el dia recortado por el clamp de fin de mes)."""

    id: int
    name: str
    importance: Importance
    category_id: int
    notify: bool
    repeat_mode: RepeatMode | None
    scheduled_date: datetime | None
    repeat_date: datetime | None
    duration_minutes: int
    add_to_checklist: bool
    detail: str | None
    occurrence_at: datetime
    """Instante exacto de la ocurrencia, en UTC. Sirve para ordenar."""
    occurrence_local: datetime
    """La misma ocurrencia en hora de pared del usuario, sin offset. Es lo
    que el front usa para decidir en que dia y a que hora pintarla: asi no
    repite la conversion de zona (que haria con la del navegador, no con la
    del usuario)."""


class CldTaskChecklistSyncRead(BaseModel):
    task: CldTaskRead
    added_to_current_week: bool
