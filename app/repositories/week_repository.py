"""Interfaz (Protocol) del acceso a datos de semanas de checklist."""

from typing import Protocol, Sequence

from app.db.models.checklist import ChecklistWeek


class WeekRepository(Protocol):
    def get_current_open(self, user_id: int) -> ChecklistWeek | None: ...

    def get_latest(self, user_id: int) -> ChecklistWeek | None: ...

    def get(self, week_id: int) -> ChecklistWeek | None: ...

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

    def commit(self) -> None: ...

    def refresh(self, week: ChecklistWeek) -> None: ...
