"""Logica de negocio de tareas concretas de una semana de checklist (no las de
template). Las rutas dependen de esto, nunca del repository directamente."""

from datetime import datetime, timezone
from typing import Sequence

from app.db.models.checklist import ChecklistTask
from app.repositories.task_repository import TaskRepository
from app.repositories.week_repository import WeekRepository
from app.schemas.checklist import TaskStatus
from app.services.week_service import WeekNotFoundError


class TaskNotFoundError(Exception):
    """La tarea solicitada no existe (o no es del usuario)."""


class WeekClosedError(Exception):
    """La semana ya esta cerrada: sus tareas no se pueden modificar."""


class ChecklistTaskService:
    def __init__(self, task_repository: TaskRepository, week_repository: WeekRepository) -> None:
        self._task_repository = task_repository
        self._week_repository = week_repository

    def list_tasks_for_week(self, user_id: int, week_id: int) -> Sequence[ChecklistTask]:
        week = self._week_repository.get(week_id)
        if week is None or week.user_id != user_id:
            raise WeekNotFoundError(week_id)
        return self._task_repository.list_by_week(week_id)

    def update_status(self, user_id: int, task_id: int, status: TaskStatus) -> ChecklistTask:
        task = self._task_repository.get(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        week = self._week_repository.get(task.cl_week_id)
        if week is None or week.user_id != user_id:
            raise TaskNotFoundError(task_id)
        if week.closed:
            raise WeekClosedError(week.id)

        task.status = status.value
        task.last_modified_date = datetime.now(timezone.utc)
        self._task_repository.commit()
        self._task_repository.refresh(task)
        return task
