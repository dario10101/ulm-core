"""Logica de negocio de semanas de checklist. Las rutas dependen de esto,
nunca del repository directamente."""

from datetime import date, datetime, timezone

from app.db.models.checklist import ChecklistTask, ChecklistWeek
from app.repositories.task_repository import TaskRepository
from app.repositories.template_task_repository import TemplateTaskRepository
from app.repositories.week_repository import WeekRepository
from app.schemas.checklist import POINTS_BY_IMPORTANCE, Importance, TaskStatus
from app.services.day_utils import parse_days

WEEK_LENGTH_DAYS = 7


class InvalidWeekRangeError(Exception):
    """El rango elegido no cubre exactamente 7 dias."""


class WeekAlreadyOpenError(Exception):
    """Ya existe una semana sin cerrar; hay que cerrarla antes de crear otra."""


class WeekNotFoundError(Exception):
    """La semana solicitada no existe (o no es del usuario)."""


class WeekAlreadyClosedError(Exception):
    """La semana ya fue cerrada, no se puede cerrar de nuevo."""


class WeekService:
    def __init__(
        self,
        week_repository: WeekRepository,
        task_repository: TaskRepository,
        template_task_repository: TemplateTaskRepository,
    ) -> None:
        self._week_repository = week_repository
        self._task_repository = task_repository
        self._template_task_repository = template_task_repository

    def get_current_week(self, user_id: int) -> ChecklistWeek | None:
        """La semana "actual" es la ultima sin cerrar, sin importar si la fecha
        de hoy cae dentro de su rango: una semana vencida sigue apareciendo
        hasta que el usuario la cierre explicitamente."""
        return self._week_repository.get_current_open(user_id)

    def create_week(self, user_id: int, first_day: date, last_day: date) -> ChecklistWeek:
        if (last_day - first_day).days != WEEK_LENGTH_DAYS - 1:
            raise InvalidWeekRangeError()
        if self._week_repository.get_current_open(user_id) is not None:
            raise WeekAlreadyOpenError()

        week = ChecklistWeek(
            user_id=user_id, first_day=first_day, last_day=last_day, closed=False
        )
        self._week_repository.add(week)
        self._week_repository.commit()
        self._week_repository.refresh(week)

        # El template no se modifica nunca al generar una semana: se copian sus
        # tareas a cl_tasks, una fila por cada dia al que aplican.
        for template_task in self._template_task_repository.list_by_user(user_id):
            for day in parse_days(template_task.day_of_week):
                self._task_repository.add(
                    ChecklistTask(
                        cl_week_id=week.id,
                        name=template_task.name,
                        day_of_week=str(day),
                        importance=template_task.importance,
                        category_id=template_task.category_id,
                        status=TaskStatus.PENDING.value,
                    )
                )
        self._task_repository.commit()
        return week

    def close_week(self, user_id: int, week_id: int) -> ChecklistWeek:
        week = self._get_owned_week(week_id, user_id)
        if week.closed:
            raise WeekAlreadyClosedError()

        tasks = self._task_repository.list_by_week(week_id)
        score = sum(
            POINTS_BY_IMPORTANCE[Importance(task.importance)]
            for task in tasks
            if task.status == TaskStatus.COMPLETE.value
        )

        week.closed = True
        week.closed_date = datetime.now(timezone.utc)
        week.score = score
        self._week_repository.commit()
        self._week_repository.refresh(week)
        return week

    def _get_owned_week(self, week_id: int, user_id: int) -> ChecklistWeek:
        week = self._week_repository.get(week_id)
        if week is None or week.user_id != user_id:
            raise WeekNotFoundError(week_id)
        return week
