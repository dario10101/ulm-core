"""Interfaz (Protocol) del acceso a datos de tareas concretas de una semana de checklist."""

from collections.abc import Sequence
from typing import Protocol

from app.db.models.checklist import ChecklistTask


class TaskRepository(Protocol):
    def list_by_week(self, week_id: int) -> Sequence[ChecklistTask]:
        """Todas las tareas de la semana, sin filtrar por status de categoria.
        Uso interno de WeekService.close_week: una tarea de una categoria ya
        deshabilitada igual debe sumar a su puntaje historico."""
        ...

    def list_visible_by_week(self, week_id: int) -> Sequence[ChecklistTask]:
        """Solo tareas de categorias ENABLED: lo que se muestra en la UI del
        checklist (GET /weeks/{id}/tasks)."""
        ...

    def get(self, task_id: int) -> ChecklistTask | None: ...

    def flush(self) -> None:
        """Manda los INSERT/UPDATE pendientes a la base sin cerrar la
        transaccion. Sirve para obtener los ids autogenerados; el commit lo
        hace `get_db` al final del request."""
        ...

    def add(self, task: ChecklistTask) -> None: ...

    def delete(self, task: ChecklistTask) -> None: ...
