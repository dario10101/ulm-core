"""Interfaz (Protocol) del acceso a datos de tareas concretas de una semana de checklist."""

from typing import Protocol, Sequence

from app.db.models.checklist import ChecklistTask


class TaskRepository(Protocol):
    def list_by_week(self, week_id: int) -> Sequence[ChecklistTask]: ...

    def get(self, task_id: int) -> ChecklistTask | None: ...

    def add(self, task: ChecklistTask) -> None: ...

    def commit(self) -> None: ...

    def refresh(self, task: ChecklistTask) -> None: ...
