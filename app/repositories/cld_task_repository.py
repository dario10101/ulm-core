"""Interfaz (Protocol) del acceso a datos de tareas de calendario (cld_tasks)."""

from typing import Protocol, Sequence

from app.db.models.cld_task import CldTask


class CldTaskRepository(Protocol):
    def list_sync_enabled(self, user_id: int) -> Sequence[CldTask]:
        """Solo tareas de categorias ENABLED (add_to_checklist=True)."""
        ...

    def list_by_user(self, user_id: int) -> Sequence[CldTask]:
        """Solo tareas de categorias ENABLED."""
        ...

    def get(self, task_id: int) -> CldTask | None: ...

    def add(self, task: CldTask) -> None: ...

    def delete(self, task: CldTask) -> None: ...

    def commit(self) -> None: ...

    def refresh(self, task: CldTask) -> None: ...
