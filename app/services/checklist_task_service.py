"""Logica de negocio de tareas concretas de una semana de checklist (no las de
template). Las rutas dependen de esto, nunca del repository directamente."""

from datetime import UTC, datetime

from app.db.models.checklist import ChecklistTask
from app.repositories.category_repository import CategoryRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.week_repository import WeekRepository
from app.schemas.checklist import CategoryStatus, Importance, TaskRead, TaskStatus
from app.services.errors import (
    CategoryNotFoundError,
    TaskNotFoundError,
    WeekClosedError,
    WeekNotFoundError,
)
from app.services.mappers import checklist_task_to_read


class ChecklistTaskService:
    def __init__(
        self,
        task_repository: TaskRepository,
        week_repository: WeekRepository,
        category_repository: CategoryRepository,
    ) -> None:
        self._task_repository = task_repository
        self._week_repository = week_repository
        self._category_repository = category_repository

    def list_tasks_for_week(self, user_id: int, week_id: int) -> list[TaskRead]:
        week = self._week_repository.get(week_id)
        if week is None or week.user_id != user_id:
            raise WeekNotFoundError(week_id)
        return [
            checklist_task_to_read(t) for t in self._task_repository.list_visible_by_week(week_id)
        ]

    def create_task(
        self,
        user_id: int,
        week_id: int,
        *,
        name: str,
        importance: Importance,
        category_id: int,
        day_of_week: int,
        detail: str | None = None,
    ) -> TaskRead:
        """Tarea circunstancial agregada directamente a la semana (no viene del
        template y no lo modifica): sirve para algo puntual de esta semana que
        no vale la pena generalizar."""
        week = self._week_repository.get(week_id)
        if week is None or week.user_id != user_id:
            raise WeekNotFoundError(week_id)
        if week.closed:
            raise WeekClosedError(week.id)

        category = self._category_repository.get(category_id)
        if (
            category is None
            or category.user_id != user_id
            or category.status != CategoryStatus.ENABLED.value
        ):
            raise CategoryNotFoundError(category_id)

        task = ChecklistTask(
            cl_week_id=week.id,
            name=name,
            day_of_week=str(day_of_week),
            importance=importance.value,
            category_id=category_id,
            detail=detail,
            status=TaskStatus.PENDING.value,
        )
        self._task_repository.add(task)
        self._task_repository.flush()
        return checklist_task_to_read(task)

    def update_status(self, user_id: int, task_id: int, status: TaskStatus) -> TaskRead:
        task = self._get_owned_open_task(user_id, task_id)

        task.status = status.value
        task.last_modified_date = datetime.now(UTC)
        self._task_repository.flush()
        return checklist_task_to_read(task)

    def update_task(
        self,
        user_id: int,
        task_id: int,
        *,
        name: str,
        importance: Importance,
        category_id: int,
        detail: str | None = None,
    ) -> TaskRead:
        """Edicion de nombre/importancia/categoria/detalle de una tarea de
        semana (modo Edit del checklist). No cambia el dia ni la semana."""
        task = self._get_owned_open_task(user_id, task_id)

        category = self._category_repository.get(category_id)
        if (
            category is None
            or category.user_id != user_id
            or category.status != CategoryStatus.ENABLED.value
        ):
            raise CategoryNotFoundError(category_id)

        task.name = name
        task.importance = importance.value
        task.category_id = category_id
        task.detail = detail
        task.last_modified_date = datetime.now(UTC)
        self._task_repository.flush()
        return checklist_task_to_read(task)

    def delete_task(self, user_id: int, task_id: int) -> None:
        task = self._get_owned_open_task(user_id, task_id)
        self._task_repository.delete(task)
        self._task_repository.flush()

    def _get_owned_open_task(self, user_id: int, task_id: int) -> ChecklistTask:
        task = self._task_repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        week = self._week_repository.get(task.cl_week_id)
        if week is None or week.user_id != user_id:
            raise TaskNotFoundError(task_id)
        if week.closed:
            raise WeekClosedError(week.id)

        return task
