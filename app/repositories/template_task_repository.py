"""Interfaz (Protocol) del acceso a datos de tareas de template de checklist."""

from collections.abc import Sequence
from typing import Protocol

from app.db.models.checklist import ChecklistTemplateTask


class TemplateTaskRepository(Protocol):
    def list_by_user(self, user_id: int) -> Sequence[ChecklistTemplateTask]:
        """Solo tareas de categorias con status ENABLED."""
        ...

    def get(self, task_id: int) -> ChecklistTemplateTask | None: ...

    def flush(self) -> None:
        """Manda los INSERT/UPDATE pendientes a la base sin cerrar la
        transaccion. Sirve para obtener los ids autogenerados; el commit lo
        hace `get_db` al final del request."""
        ...

    def add(self, task: ChecklistTemplateTask) -> None: ...

    def delete(self, task: ChecklistTemplateTask) -> None: ...

    def category_belongs_to_user(self, category_id: int, user_id: int) -> bool:
        """True solo si la categoria es del usuario y esta ENABLED."""
        ...
