"""Rutas de eventos de calendario: lectura de festivos/eventos generales mas
los personales del usuario, y alta/edicion/borrado de los personales
(cld_user_events). Los generales se administran en /system/calendar-events."""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import (
    get_calendar_event_service,
    get_cld_user_event_service,
    get_current_user_id,
)
from app.api.errors import http_error
from app.schemas.calendar_event import (
    CalendarEventMarkerRead,
    CalendarEventRangeRead,
    CldUserEventRead,
    CldUserEventWrite,
)
from app.services.calendar_event_service import CalendarEventService
from app.services.cld_user_event_service import CldUserEventService
from app.services.errors import DomainError

router = APIRouter(prefix="/calendar-events", tags=["calendar-events"])


@router.get("", response_model=list[CalendarEventMarkerRead])
def list_calendar_events(
    first_day: date = Query(),
    last_day: date = Query(),
    user_id: int = Depends(get_current_user_id),
    service: CalendarEventService = Depends(get_calendar_event_service),
) -> list[CalendarEventMarkerRead]:
    return service.list_markers(user_id, first_day, last_day)


@router.get("/ranges", response_model=list[CalendarEventRangeRead])
def list_calendar_event_ranges(
    first_day: date = Query(),
    last_day: date = Query(),
    user_id: int = Depends(get_current_user_id),
    service: CalendarEventService = Depends(get_calendar_event_service),
) -> list[CalendarEventRangeRead]:
    """Rangos completos (sin recortar a inicio/fin), para pintar cada dia
    que un evento cubre (vista mensual)."""
    return service.list_ranges(user_id, first_day, last_day)


@router.get("/user-event-codes", response_model=list[str])
def list_user_event_codes(
    user_id: int = Depends(get_current_user_id),
    service: CldUserEventService = Depends(get_cld_user_event_service),
) -> list[str]:
    """Tipos que el usuario ya uso, para el selector del formulario."""
    return service.list_codes(user_id)


@router.post("/user-events", response_model=CldUserEventRead, status_code=201)
def create_user_event(
    payload: CldUserEventWrite,
    user_id: int = Depends(get_current_user_id),
    service: CldUserEventService = Depends(get_cld_user_event_service),
) -> CldUserEventRead:
    try:
        return service.create(user_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/user-events/{event_id}", response_model=CldUserEventRead)
def update_user_event(
    event_id: int,
    payload: CldUserEventWrite,
    user_id: int = Depends(get_current_user_id),
    service: CldUserEventService = Depends(get_cld_user_event_service),
) -> CldUserEventRead:
    try:
        return service.update(user_id, event_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/user-events/{event_id}", status_code=204)
def delete_user_event(
    event_id: int,
    user_id: int = Depends(get_current_user_id),
    service: CldUserEventService = Depends(get_cld_user_event_service),
) -> None:
    try:
        service.delete(user_id, event_id)
    except DomainError as exc:
        raise http_error(exc)
