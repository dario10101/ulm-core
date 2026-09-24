"""Interfaz (Protocol) del acceso a datos de semanas de checklist."""

from collections.abc import Sequence
from typing import Protocol

from app.db.models.checklist import ChecklistWeek


class WeekRepository(Protocol):
    def get_current_open(self, user_id: int) -> ChecklistWeek | None: ...

    def get_latest(self, user_id: int) -> ChecklistWeek | None: ...

    def get(self, week_id: int) -> ChecklistWeek | None: ...

    def flush(self) -> None:
        """Manda los INSERT/UPDATE pendientes a la base sin cerrar la
        transaccion. Sirve para obtener los ids autogenerados; el commit lo
        hace `get_db` al final del request."""
        ...

    def add(self, week: ChecklistWeek) -> None: ...

    def list_closed_by_year(self, user_id: int, year: int) -> Sequence[ChecklistWeek]:
        """Semanas cerradas cuyo first_day cae en `year` (vista semanal: cada
        semana pertenece al anio de su propio inicio, sin desagregar)."""
        ...

    def list_closed_overlapping_year(self, user_id: int, year: int) -> Sequence[ChecklistWeek]:
        """Semanas cerradas cuyo rango [first_day, last_day] toca `year`,
        incluyendo las que cruzan fin de anio (vista mensual: cada dia se
        desagrega despues a su mes/anio real, ver ChecklistAnalyticsService)."""
        ...
