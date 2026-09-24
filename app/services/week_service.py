"""Logica de negocio de semanas de checklist. Las rutas dependen de esto,
nunca del repository directamente."""

from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.db.models.checklist import ChecklistTask, ChecklistWeek, ChecklistWeekCategoryDayScore
from app.repositories.category_repository import CategoryRepository
from app.repositories.cld_task_repository import CldTaskRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.template_task_repository import TemplateTaskRepository
from app.repositories.week_category_day_score_repository import WeekCategoryDayScoreRepository
from app.repositories.week_repository import WeekRepository
from app.schemas.checklist import (
    POINTS_BY_IMPORTANCE,
    CategoryStatus,
    Importance,
    TaskStatus,
    WeekRead,
)
from app.services.cld_task_sync import build_checklist_task_for_week
from app.services.day_utils import parse_days
from app.services.errors import (
    InvalidWeekRangeError,
    WeekAlreadyClosedError,
    WeekAlreadyOpenError,
    WeekEndInThePastError,
    WeekHasPendingTasksError,
    WeekNotFoundError,
    WeekStartTooEarlyError,
)
from app.services.mappers import week_to_read

MAX_WEEK_DAYS = 7


class WeekService:
    def __init__(
        self,
        week_repository: WeekRepository,
        task_repository: TaskRepository,
        template_task_repository: TemplateTaskRepository,
        cld_task_repository: CldTaskRepository,
        score_repository: WeekCategoryDayScoreRepository,
        category_repository: CategoryRepository,
    ) -> None:
        self._week_repository = week_repository
        self._task_repository = task_repository
        self._template_task_repository = template_task_repository
        self._cld_task_repository = cld_task_repository
        self._score_repository = score_repository
        self._category_repository = category_repository

    def get_current_week(self, user_id: int) -> WeekRead | None:
        """La semana "actual" es la ultima sin cerrar, sin importar si la fecha
        de hoy cae dentro de su rango: una semana vencida sigue apareciendo
        hasta que el usuario la cierre explicitamente."""
        week = self._week_repository.get_current_open(user_id)
        return week_to_read(week) if week is not None else None

    def get_next_range(self, user_id: int) -> tuple[date, date]:
        """Limites minimos para la proxima semana: el primer dia no puede ser
        anterior al dia siguiente al ultimo dia de la semana mas reciente (o a
        MAX_WEEK_DAYS dias atras de hoy si todavia no hay ninguna semana), y
        el ultimo dia no puede ser anterior a hoy."""
        today = date.today()
        previous_week = self._week_repository.get_latest(user_id)
        min_first_day = (
            previous_week.last_day + timedelta(days=1)
            if previous_week is not None
            else today - timedelta(days=MAX_WEEK_DAYS)
        )
        return min_first_day, today

    def create_week(self, user_id: int, first_day: date, last_day: date, tz: ZoneInfo) -> WeekRead:
        if not (0 <= (last_day - first_day).days <= MAX_WEEK_DAYS - 1):
            raise InvalidWeekRangeError()
        if self._week_repository.get_current_open(user_id) is not None:
            raise WeekAlreadyOpenError()

        min_first_day, min_last_day = self.get_next_range(user_id)
        if last_day < min_last_day:
            raise WeekEndInThePastError()
        if first_day < min_first_day:
            raise WeekStartTooEarlyError(min_first_day)

        week = ChecklistWeek(user_id=user_id, first_day=first_day, last_day=last_day, closed=False)
        self._week_repository.add(week)
        # flush y no commit: hace falta el id de la semana para colgarle las
        # tareas. El commit lo hace get_db al cerrar el request.
        self._week_repository.flush()

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

        # Tareas de calendario (cld_tasks) con add_to_checklist=True: se
        # re-evaluan en cada semana nueva, sin tocar el template tampoco aca.
        for cld_task in self._cld_task_repository.list_sync_enabled(user_id):
            checklist_task = build_checklist_task_for_week(cld_task, week, tz)
            if checklist_task is not None:
                self._task_repository.add(checklist_task)

        self._task_repository.flush()
        return week_to_read(week)

    def close_week(self, user_id: int, week_id: int) -> WeekRead:
        week = self._get_owned_week(week_id, user_id)
        if week.closed:
            raise WeekAlreadyClosedError()

        # Todas las tareas de la semana, incluidas las de categorias ya
        # deshabilitadas: esas siguen sumando a su puntaje historico tal como
        # estan, solo no bloquean el cierre (el usuario no tiene forma de
        # marcarlas desde la UI, que ya no las muestra).
        tasks = self._task_repository.list_by_week(week_id)
        disabled_category_ids = self._disabled_category_ids(user_id, tasks)
        pending_count = sum(
            1
            for task in tasks
            if task.status == TaskStatus.PENDING.value
            and task.category_id not in disabled_category_ids
        )
        if pending_count > 0:
            raise WeekHasPendingTasksError(pending_count)

        score = sum(
            POINTS_BY_IMPORTANCE[Importance(task.importance)]
            for task in tasks
            if task.status == TaskStatus.COMPLETE.value
        )

        week.closed = True
        week.closed_date = datetime.now(UTC)
        week.score = score
        self._save_category_day_scores(week.id, tasks)
        self._week_repository.flush()
        return week_to_read(week)

    def _disabled_category_ids(self, user_id: int, tasks: list[ChecklistTask]) -> set[int]:
        category_ids = {task.category_id for task in tasks}
        categories = self._category_repository.list_by_ids(user_id, list(category_ids))
        return {
            category.id
            for category in categories
            if category.status != CategoryStatus.ENABLED.value
        }

    def _save_category_day_scores(self, week_id: int, tasks: list[ChecklistTask]) -> None:
        """Materializa cl_week_category_day_score al cerrar la semana: una
        semana cerrada es inmutable, asi que este es el unico momento en que
        vale la pena calcular este agregado (evita recalcularlo en cada
        consulta de analytics, potencialmente escaneando anios de cl_tasks).

        Grano (categoria, dia): el mas fino que sigue siendo generico —
        cualquier rollup mas grueso (semanal, mensual, por dia de la semana)
        sale de sumar estas pocas filas, sin volver a tocar cl_tasks."""
        totals: dict[tuple[int, int], dict[str, int]] = defaultdict(
            lambda: {"score": 0, "points_possible": 0}
        )
        for task in tasks:
            points = POINTS_BY_IMPORTANCE[Importance(task.importance)]
            key = (task.category_id, int(task.day_of_week))
            totals[key]["points_possible"] += points
            if task.status == TaskStatus.COMPLETE.value:
                totals[key]["score"] += points

        for (category_id, day_of_week), totals_for_key in totals.items():
            self._score_repository.add(
                ChecklistWeekCategoryDayScore(
                    cl_week_id=week_id,
                    category_id=category_id,
                    day_of_week=day_of_week,
                    score=totals_for_key["score"],
                    points_possible=totals_for_key["points_possible"],
                )
            )

    def _get_owned_week(self, week_id: int, user_id: int) -> ChecklistWeek:
        week = self._week_repository.get(week_id)
        if week is None or week.user_id != user_id:
            raise WeekNotFoundError(week_id)
        return week
