"""Interfaz (Protocol) del acceso a datos de eventos generales (cld_events)."""

from datetime import date
from typing import Protocol, Sequence

from app.db.models.cld_event import CldEvent


class CldEventRepository(Protocol):
    def list_in_range(self, range_start: date, range_end: date) -> Sequence[CldEvent]: ...
