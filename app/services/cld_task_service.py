"""Logica de negocio de tareas de calendario (cld_tasks): tareas puntuales o
recurrentes, con sincronizacion opcional hacia el checklist semanal (sin
tocar nunca el template). Las rutas dependen de esto, nunca del repository
directamente.

Zona horaria: las fechas entran y salen de este service en hora de pared del
usuario (naive); la conversion a/desde UTC (que es lo que guarda la BD) pasa
aca adentro, usando la zona que llega por parametro. Ver cld_task_sync.
"""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.db.models.cld_task import CldTask
from app.repositories.category_repository import CategoryRepository
from app.repositories.cld_task_repository import CldTaskRepository
from app.repositories.task_repository import TaskRepository
from app.repositories.week_repository import WeekRepository
from app.schemas.checklist import CategoryStatus, Importance
from app.schemas.cld_task import CldTaskOccurrenceRead, CldTaskRead, RepeatMode
from app.services.cld_task_sync import (
    build_checklist_task,
    build_checklist_task_for_week,
    occurrences_in_range,
    parse_excluded_dates,
    serialize_excluded_dates,
    to_utc,
)
from app.services.errors import CategoryNotFoundError, CldTaskNotFoundError, InvalidTaskDateError
from app.services.mappers import cld_task_occurrence_to_read, cld_task_to_read


class CldTaskService:
    def __init__(
        self,
        cld_task_repository: CldTaskRepository,
        category_repository: CategoryRepository,
        week_repository: WeekRepository,
        task_repository: TaskRepository,
    ) -> None:
        self._cld_task_repository = cld_task_repository
        self._category_repository = category_repository
        self._week_repository = week_repository
        self._task_repository = task_repository

    def create_task(
        self,
        user_id: int,
        tz: ZoneInfo,
        *,
        name: str,
        importance: Importance,
        category_id: int,
        notify: bool,
        repeat_mode: RepeatMode | None,
        scheduled_date: datetime | None,
        repeat_date: datetime | None,
        duration_minutes: int,
        add_to_checklist: bool,
        detail: str | None = None,
    ) -> CldTaskRead:
        """`scheduled_date`/`repeat_date` llegan en hora de pared del usuario
        (el schema rechaza un datetime con tzinfo) y se guardan en UTC."""
        category = self._category_repository.get(category_id)
        if (
            category is None
            or category.user_id != user_id
            or category.status != CategoryStatus.ENABLED.value
        ):
            raise CategoryNotFoundError(category_id)

        task = CldTask(
            user_id=user_id,
            category_id=category_id,
            name=name,
            importance=importance.value,
            notify=notify,
            scheduled_date=to_utc(scheduled_date, tz) if scheduled_date else None,
            repeat_mode=repeat_mode.value if repeat_mode else None,
            repeat_date=to_utc(repeat_date, tz) if repeat_date else None,
            duration_minutes=duration_minutes,
            add_to_checklist=add_to_checklist,
            detail=detail,
        )
        self._cld_task_repository.add(task)
        self._cld_task_repository.flush()

        if add_to_checklist:
            self._sync_to_current_week(user_id, task, tz)

        return cld_task_to_read(task, tz)

    def list_for_range(
        self, user_id: int, first_day: date, last_day: date, tz: ZoneInfo
    ) -> list[CldTaskOccurrenceRead]:
        """Ocurrencias de todas las tareas del usuario que caen en
        [first_day, last_day], entendidos como dias locales del usuario y ya
        descontando las excluidas. first_day == last_day cubre el caso de un
        solo dia (vista diaria); un rango de 7 dias cubre la vista semanal;
        un mes completo cubre la mensual (una tarea recurrente puede aparecer
        varias veces en ese caso)."""
        occurrences: list[CldTaskOccurrenceRead] = []
        for task in self._cld_task_repository.list_by_user(user_id):
            for occurrence in occurrences_in_range(task, first_day, last_day, tz):
                occurrences.append(cld_task_occurrence_to_read(task, occurrence, tz))
        return occurrences

    def list_for_day(self, user_id: int, day: date, tz: ZoneInfo) -> list[CldTaskOccurrenceRead]:
        return self.list_for_range(user_id, day, day, tz)

    def update_task(
        self,
        user_id: int,
        task_id: int,
        tz: ZoneInfo,
        *,
        name: str,
        importance: Importance,
        category_id: int,
        notify: bool,
        detail: str | None,
        scheduled_date: datetime | None,
        repeat_date: datetime | None,
        duration_minutes: int,
    ) -> CldTaskRead:
        """Edicion de una tarea de calendario. No cambia repeat_mode ni
        add_to_checklist (no se exponen como parametros a proposito)."""
        task = self._get_owned_task(user_id, task_id)

        category = self._category_repository.get(category_id)
        if (
            category is None
            or category.user_id != user_id
            or category.status != CategoryStatus.ENABLED.value
        ):
            raise CategoryNotFoundError(category_id)

        if task.repeat_mode is None:
            if scheduled_date is None or repeat_date is not None:
                raise InvalidTaskDateError()
            task.scheduled_date = to_utc(scheduled_date, tz)
        else:
            if repeat_date is None or scheduled_date is not None:
                raise InvalidTaskDateError()
            task.repeat_date = to_utc(repeat_date, tz)

        task.name = name
        task.importance = importance.value
        task.category_id = category_id
        task.notify = notify
        task.duration_minutes = duration_minutes
        task.detail = detail
        task.last_modified_date = datetime.now(UTC)
        self._cld_task_repository.flush()
        return cld_task_to_read(task, tz)

    def delete_task(self, user_id: int, task_id: int, occurrence_date: date | None = None) -> None:
        """Si occurrence_date viene y la tarea repite, borra solo esa
        ocurrencia (la agrega a excluded_dates, que son dias locales del
        usuario). En cualquier otro caso borra la tarea completa (y con ella
        toda la serie, si aplica)."""
        task = self._get_owned_task(user_id, task_id)

        if occurrence_date is not None and task.repeat_mode is not None:
            excluded = parse_excluded_dates(task.excluded_dates)
            excluded.add(occurrence_date)
            task.excluded_dates = serialize_excluded_dates(excluded)
            self._cld_task_repository.flush()
            return

        self._cld_task_repository.delete(task)
        self._cld_task_repository.flush()

    def enable_checklist_sync(
        self, user_id: int, task_id: int, occurrence_date: date, tz: ZoneInfo
    ) -> tuple[CldTaskRead, bool]:
        """Marca add_to_checklist=True (siempre, aunque no se pueda agregar
        ahora mismo) e intenta agregar esta ocurrencia puntual a la semana
        abierta actual. El bool indica si se agrego ahora o quedara pendiente
        para cuando se cree una semana que cubra occurrence_date.

        `occurrence_date` ya es un dia local del usuario (viene del front,
        que a su vez lo recibio calculado por el backend)."""
        task = self._get_owned_task(user_id, task_id)
        task.add_to_checklist = True
        self._cld_task_repository.flush()

        week = self._week_repository.get_current_open(user_id)
        if week is None or not (week.first_day <= occurrence_date <= week.last_day):
            return cld_task_to_read(task, tz), False

        self._task_repository.add(build_checklist_task(task, week.id, occurrence_date))
        self._task_repository.flush()
        return cld_task_to_read(task, tz), True

    def _sync_to_current_week(self, user_id: int, task: CldTask, tz: ZoneInfo) -> None:
        """Si hay una semana sin cerrar y la ocurrencia de esta tarea cae
        dentro de su rango, la agrega ahora mismo. Si no hay semana abierta o
        la fecha no cae en ese rango, no hace nada: se vuelve a evaluar cada
        vez que se crea una semana nueva (ver WeekService.create_week)."""
        week = self._week_repository.get_current_open(user_id)
        if week is None:
            return

        checklist_task = build_checklist_task_for_week(task, week, tz)
        if checklist_task is None:
            return

        self._task_repository.add(checklist_task)
        self._task_repository.flush()

    def _get_owned_task(self, user_id: int, task_id: int) -> CldTask:
        task = self._cld_task_repository.get(task_id)
        if task is None or task.user_id != user_id:
            raise CldTaskNotFoundError(task_id)
        return task
