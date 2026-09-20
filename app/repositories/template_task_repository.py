"""Interfaz (Protocol) del acceso a datos de tareas de template de checklist."""

from typing import Protocol, Sequence

from app.db.models.checklist import ChecklistTemplateTask


class TemplateTaskRepository(Protocol):
    def list_by_user(self, user_id: int) -> Sequence[ChecklistTemplateTask]:
        """Solo tareas de categorias con status ENABLED."""
        ...

    def get(self, task_id: int) -> ChecklistTemplateTask | None: ...

    def add(self, task: ChecklistTemplateTask) -> None: ...

    def delete(self, task: ChecklistTemplateTask) -> None: ...

    def category_belongs_to_user(self, category_id: int, user_id: int) -> bool:
        """True solo si la categoria es del usuario y esta ENABLED."""
        ...

    def commit(self) -> None: ...

    def refresh(self, task: ChecklistTemplateTask) -> None: ...
