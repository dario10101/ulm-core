"""Festivos oficiales calculados por una libreria (python-holidays).

Son la *base* que el admin ajusta en Settings -> Calendar events: lo que de
verdad pinta el calendario es la tabla cld_events. CalendarAdminService
depende del Protocol, asi los tests le pasan una lista fija y no dependen de
la version de la libreria ni de una ley nueva que mueva un festivo.
"""

from dataclasses import dataclass
from datetime import date
from typing import Protocol

import holidays


@dataclass(frozen=True)
class OfficialHoliday:
    day: date
    name: str


class HolidayProvider(Protocol):
    country: str

    def for_year(self, year: int) -> list[OfficialHoliday]:
        """Festivos del año, ordenados por fecha."""
        ...


class PythonHolidaysProvider:
    def __init__(self, *, country: str, language: str) -> None:
        self.country = country
        self._language = language

    def for_year(self, year: int) -> list[OfficialHoliday]:
        calendar = holidays.country_holidays(self.country, years=year, language=self._language)
        # La libreria marca los trasladados por la ley Emiliani con
        # "(observado)": para el usuario es simplemente el festivo de ese dia.
        return [
            OfficialHoliday(day=day, name=_clean_name(name))
            for day, name in sorted(calendar.items())
        ]


def _clean_name(name: str) -> str:
    for suffix in (" (observado)", " (observed)"):
        name = name.removesuffix(suffix)
    return name
