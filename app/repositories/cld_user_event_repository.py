"""Interfaz (Protocol) del acceso a datos de eventos personales (cld_user_events)."""

from datetime import date
from typing import Protocol, Sequence

from app.db.models.cld_user_event import CldUserEvent


class CldUserEventRepository(Protocol):
    def list_in_range(self, user_id: int, range_start: date, range_end: date) -> Sequence[CldUserEvent]:
        """Solo eventos de categorias ENABLED."""
        ...
