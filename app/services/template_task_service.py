"""Logica de negocio de tareas de template de checklist. Las rutas dependen de
esto, nunca del repository directamente.

Estrategia para tareas que aplican a varios dias (dias guardados como CSV en
una sola fila, ej. "1,2,4"): al editar o eliminar la tarea *para un dia
puntual*, ese dia se separa de la fila original:
  - Si la fila tenia un unico dia, se edita/elimina in place.
  - Si tenia varios dias: el dia editado se quita de la fila original (que
    conserva sin cambios el resto de los dias) y se crea una fila nueva solo
    para ese dia con los valores nuevos. Al eliminar, el dia simplemente se
    quita de la fila original (o se borra la fila si era el ultimo dia).
Asi una edicion/eliminacion en un dia nunca afecta los demas dias.
"""

from typing import Sequence

from app.db.models.checklist import ChecklistTemplateTask
from app.repositories.template_task_repository import TemplateTaskRepository
from app.schemas.checklist import Importance
from app.services.day_utils import parse_days, serialize_days


class TemplateTaskNotFoundError(Exception):
    """La tarea (o el dia solicitado dentro de ella) no existe para este usuario."""


class CategoryNotFoundError(Exception):
    """La categoria referenciada no existe (o no es del usuario)."""

    def __init__(self, category_id: int) -> None:
        self.category_id = category_id


class TemplateTaskService:
    def __init__(self, repository: TemplateTaskRepository) -> None:
        self._repository = repository

    def list_tasks(self, user_id: int) -> Sequence[ChecklistTemplateTask]:
        return self._repository.list_by_user(user_id)

    def create_task(
        self,
        *,
        user_id: int,
        name: str,
        importance: Importance,
        category_id: int,
        days: list[int],
        detail: str | None = None,
    ) -> ChecklistTemplateTask:
        if not self._repository.category_belongs_to_user(category_id, user_id):
            raise CategoryNotFoundError(category_id)

        task = ChecklistTemplateTask(
            name=name,
            day_of_week=serialize_days(days),
            importance=importance.value,
            category_id=category_id,
            detail=detail,
        )
        self._repository.add(task)
        self._repository.commit()
        self._repository.refresh(task)
        return task

    def update_task_for_day(
        self,
        task_id: int,
        day: int,
        *,
        user_id: int,
        name: str,
        importance: Importance,
        category_id: int,
        detail: str | None = None,
    ) -> ChecklistTemplateTask:
        task = self._get_owned_task(task_id, user_id)
        days = parse_days(task.day_of_week)
        if day not in days:
            raise TemplateTaskNotFoundError(task_id)
        if not self._repository.category_belongs_to_user(category_id, user_id):
            raise CategoryNotFoundError(category_id)

        remaining_days = [d for d in days if d != day]

        if not remaining_days:
            task.name = name
            task.importance = importance.value
            task.category_id = category_id
            task.detail = detail
            self._repository.commit()
            self._repository.refresh(task)
            return task

        task.day_of_week = serialize_days(remaining_days)
        split_task = ChecklistTemplateTask(
            name=name,
            day_of_week=serialize_days([day]),
            importance=importance.value,
            category_id=category_id,
            detail=detail,
        )
        self._repository.add(split_task)
        self._repository.commit()
        self._repository.refresh(split_task)
        return split_task

    def delete_task_for_day(self, task_id: int, day: int, *, user_id: int) -> None:
        task = self._get_owned_task(task_id, user_id)
        days = parse_days(task.day_of_week)
        if day not in days:
            raise TemplateTaskNotFoundError(task_id)

        remaining_days = [d for d in days if d != day]
        if not remaining_days:
            self._repository.delete(task)
        else:
            task.day_of_week = serialize_days(remaining_days)
        self._repository.commit()

    def _get_owned_task(self, task_id: int, user_id: int) -> ChecklistTemplateTask:
        task = self._repository.get(task_id)
        if task is None or not self._repository.category_belongs_to_user(task.category_id, user_id):
            raise TemplateTaskNotFoundError(task_id)
        return task
