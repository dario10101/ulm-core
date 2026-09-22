"""Rutas de eventos de calendario (festivos/eventos generales + personales
del usuario). Solo lectura: estas tablas todavia no tienen CRUD."""

from datetime import date

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_calendar_event_service, get_current_user_id
from app.schemas.calendar_event import CalendarEventMarkerRead, CalendarEventRangeRead
from app.services.calendar_event_service import CalendarEventService

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
