"""Interfaz (Protocol) del acceso a datos de semanas de checklist."""

from typing import Protocol

from app.db.models.checklist import ChecklistWeek


class WeekRepository(Protocol):
    def get_current_open(self, user_id: int) -> ChecklistWeek | None: ...

    def get(self, week_id: int) -> ChecklistWeek | None: ...

    def add(self, week: ChecklistWeek) -> None: ...

    def commit(self) -> None: ...

    def refresh(self, week: ChecklistWeek) -> None: ...
