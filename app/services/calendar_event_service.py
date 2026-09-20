"""Logica de negocio de eventos de calendario: junta festivos/eventos
generales (cld_events) y eventos personales (cld_user_events) y los expone
como marcadores de inicio/fin dentro de un rango de fechas (vista semanal)."""

from datetime import date
from typing import Sequence

from app.repositories.cld_event_repository import CldEventRepository
from app.repositories.cld_user_event_repository import CldUserEventRepository
from app.schemas.calendar_event import (
    CalendarEventMarkerRead,
    CalendarEventRangeRead,
    MarkerSource,
    MarkerType,
)


class CalendarEventService:
    def __init__(
        self,
        cld_event_repository: CldEventRepository,
        cld_user_event_repository: CldUserEventRepository,
    ) -> None:
        self._cld_event_repository = cld_event_repository
        self._cld_user_event_repository = cld_user_event_repository

    def list_markers(
        self, user_id: int, first_day: date, last_day: date
    ) -> list[CalendarEventMarkerRead]:
        markers: list[CalendarEventMarkerRead] = []

        for event in self._cld_event_repository.list_in_range(first_day, last_day):
            markers.extend(
                self._markers_for(
                    id=event.id,
                    name=event.name,
                    detail=event.detail,
                    code=event.code,
                    event_first_day=event.first_day,
                    event_last_day=event.last_day,
                    range_start=first_day,
                    range_end=last_day,
                    source=MarkerSource.EVENT,
                )
            )

        for user_event in self._cld_user_event_repository.list_in_range(user_id, first_day, last_day):
            markers.extend(
                self._markers_for(
                    id=user_event.id,
                    name=user_event.name,
                    detail=user_event.detail,
                    code=user_event.code,
                    event_first_day=user_event.first_day,
                    event_last_day=user_event.last_day,
                    range_start=first_day,
                    range_end=last_day,
                    source=MarkerSource.USER_EVENT,
                )
            )

        return sorted(markers, key=lambda m: m.marker_date)

    def list_ranges(self, user_id: int, first_day: date, last_day: date) -> list[CalendarEventRangeRead]:
        """Rangos completos (sin recortar) de los eventos que se solapan con
        [first_day, last_day]. A diferencia de list_markers, no proyecta a
        inicio/fin: sirve para pintar cada dia que un evento cubre (vista
        mensual)."""
        ranges = [
            CalendarEventRangeRead(
                id=event.id,
                name=event.name,
                detail=event.detail,
                code=event.code,
                source=MarkerSource.EVENT,
                first_day=event.first_day,
                last_day=event.last_day,
            )
            for event in self._cld_event_repository.list_in_range(first_day, last_day)
        ]
        ranges.extend(
            CalendarEventRangeRead(
                id=user_event.id,
                name=user_event.name,
                detail=user_event.detail,
                code=user_event.code,
                source=MarkerSource.USER_EVENT,
                first_day=user_event.first_day,
                last_day=user_event.last_day,
            )
            for user_event in self._cld_user_event_repository.list_in_range(user_id, first_day, last_day)
        )
        return sorted(ranges, key=lambda r: r.first_day)

    @staticmethod
    def _markers_for(
        *,
        id: int,
        name: str,
        detail: str | None,
        code: str | None,
        event_first_day: date,
        event_last_day: date,
        range_start: date,
        range_end: date,
        source: MarkerSource,
    ) -> Sequence[CalendarEventMarkerRead]:
        base = dict(id=id, name=name, detail=detail, code=code, source=source)

        if event_first_day == event_last_day:
            if range_start <= event_first_day <= range_end:
                return [CalendarEventMarkerRead(**base, marker_date=event_first_day, marker_type=MarkerType.SINGLE)]
            return []

        markers = []
        if range_start <= event_first_day <= range_end:
            markers.append(CalendarEventMarkerRead(**base, marker_date=event_first_day, marker_type=MarkerType.START))
        if range_start <= event_last_day <= range_end:
            markers.append(CalendarEventMarkerRead(**base, marker_date=event_last_day, marker_type=MarkerType.END))
        return markers
