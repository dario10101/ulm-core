"""Administracion de eventos generales del calendario (cld_events): festivos y
fechas especiales, globales para todos los usuarios. Solo el admin.

Los festivos oficiales los calcula la libreria (HolidayProvider) por año, pero
lo que pinta el calendario es siempre la tabla: la libreria solo *propone*.
El admin importa los que falten, agrega los propios y quita los que no quiera.
Un festivo oficial cuenta como cargado si hay un HOLIDAY ese mismo dia,
aunque el nombre difiera (los de antes se cargaron con otros nombres).

No se recuerda que el admin quito un festivo oficial: queda como "no
agregado" y "Add missing" lo volveria a traer. Es explicito (boton), asi que
no reaparece solo.
"""

from datetime import date

from app.db.models.cld_event import CldEvent
from app.integrations.holiday_provider import HolidayProvider
from app.repositories.cld_event_repository import CldEventRepository
from app.schemas.calendar_event import (
    CalendarYearRead,
    CldEventCode,
    CldEventRead,
    CldEventWrite,
    OfficialHolidayRead,
)
from app.services.errors import CldEventNotFoundError


class CalendarAdminService:
    def __init__(self, repository: CldEventRepository, holidays: HolidayProvider) -> None:
        self._repository = repository
        self._holidays = holidays

    def get_year(self, year: int) -> CalendarYearRead:
        events = self._repository.list_in_range(date(year, 1, 1), date(year, 12, 31))
        holiday_by_day = {e.first_day: e.id for e in events if e.code == CldEventCode.HOLIDAY.value}
        return CalendarYearRead(
            year=year,
            country=self._holidays.country,
            events=[CldEventRead.model_validate(e) for e in events],
            official_holidays=[
                OfficialHolidayRead(day=h.day, name=h.name, event_id=holiday_by_day.get(h.day))
                for h in self._holidays.for_year(year)
            ],
        )

    def import_missing_holidays(self, year: int) -> CalendarYearRead:
        for holiday in self.get_year(year).official_holidays:
            if holiday.event_id is None:
                self._repository.add(
                    CldEvent(
                        code=CldEventCode.HOLIDAY.value,
                        first_day=holiday.day,
                        last_day=holiday.day,
                        name=holiday.name,
                    )
                )
        self._repository.flush()
        return self.get_year(year)

    def create(self, payload: CldEventWrite) -> CldEventRead:
        event = CldEvent(**payload.model_dump(mode="python"))
        event.code = payload.code.value
        self._repository.add(event)
        self._repository.flush()
        return CldEventRead.model_validate(event)

    def update(self, event_id: int, payload: CldEventWrite) -> CldEventRead:
        event = self._get(event_id)
        event.code = payload.code.value
        event.first_day = payload.first_day
        event.last_day = payload.last_day
        event.name = payload.name
        event.detail = payload.detail
        self._repository.flush()
        return CldEventRead.model_validate(event)

    def delete(self, event_id: int) -> None:
        # Borrado real: nada referencia a cld_events (el calendario lo lee por rango).
        self._repository.delete(self._get(event_id))
        self._repository.flush()

    def _get(self, event_id: int) -> CldEvent:
        event = self._repository.get(event_id)
        if event is None:
            raise CldEventNotFoundError(event_id)
        return event
