"""Interfaz (Protocol) del acceso a datos de eventos generales (cld_events)."""

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.db.models.cld_event import CldEvent


class CldEventRepository(Protocol):
    def list_in_range(self, range_start: date, range_end: date) -> Sequence[CldEvent]: ...

    def get(self, event_id: int) -> CldEvent | None: ...

    def add(self, event: CldEvent) -> None: ...

    def delete(self, event: CldEvent) -> None: ...

    def flush(self) -> None: ...
