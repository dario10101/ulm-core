"""Interfaz (Protocol) del acceso a datos de eventos personales (cld_user_events)."""

from collections.abc import Sequence
from datetime import date
from typing import Protocol

from app.db.models.cld_user_event import CldUserEvent


class CldUserEventRepository(Protocol):
    def list_in_range(
        self, user_id: int, range_start: date, range_end: date
    ) -> Sequence[CldUserEvent]:
        """Solo eventos de categorias ENABLED."""
        ...

    def list_codes(self, *, user_id: int) -> list[str]:
        """Tipos (code) distintos que ya uso el usuario, ordenados. Incluye los
        de eventos en categorias DISABLED: el tipo sigue existiendo."""
        ...

    def get(self, event_id: int, *, user_id: int) -> CldUserEvent | None: ...

    def add(self, event: CldUserEvent) -> None: ...

    def delete(self, event: CldUserEvent) -> None: ...

    def flush(self) -> None: ...
