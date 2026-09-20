"""Logica compartida para sincronizar tareas de calendario (cld_tasks) con el
checklist semanal (cl_tasks). Usada tanto al crear una tarea de calendario
(ChecklistTaskService no aplica aca) como al crear una semana nueva."""

from calendar import monthrange
from datetime import date, datetime

from app.db.models.checklist import ChecklistTask, ChecklistWeek
from app.db.models.cld_task import CldTask
from app.schemas.checklist import TaskStatus


def _clamp_day(year: int, month: int, day: int) -> int:
    """Ultimo dia disponible de (year, month) si day lo excede (ej. 31 en febrero)."""
    return min(day, monthrange(year, month)[1])


def compute_occurrence_in_range(
    repeat_mode: str | None,
    anchor: datetime,
    range_start: date,
    range_end: date,
) -> date | None:
    """Fecha concreta (si existe) en la que esta tarea cae dentro de
    [range_start, range_end]. El rango siempre son 7 dias consecutivos (una
    semana de checklist), por lo que a lo sumo hay una ocurrencia."""
    if repeat_mode is None:
        occurrence = anchor.date()
        return occurrence if range_start <= occurrence <= range_end else None

    if repeat_mode == "WEEKLY":
        offset = (anchor.isoweekday() - range_start.isoweekday()) % 7
        occurrence = date.fromordinal(range_start.toordinal() + offset)
        return occurrence if occurrence <= range_end else None

    if repeat_mode == "MONTHLY":
        for year, month in {(range_start.year, range_start.month), (range_end.year, range_end.month)}:
            occurrence = date(year, month, _clamp_day(year, month, anchor.day))
            if range_start <= occurrence <= range_end:
                return occurrence
        return None

    if repeat_mode == "YEARLY":
        for year in {range_start.year, range_end.year}:
            occurrence = date(year, anchor.month, _clamp_day(year, anchor.month, anchor.day))
            if range_start <= occurrence <= range_end:
                return occurrence
        return None

    raise ValueError(f"repeat_mode desconocido: {repeat_mode}")


def _months_in_range(range_start: date, range_end: date) -> set[tuple[int, int]]:
    """Todos los pares (year, month) que el rango toca, extremos incluidos."""
    months = set()
    year, month = range_start.year, range_start.month
    while (year, month) <= (range_end.year, range_end.month):
        months.add((year, month))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


def compute_occurrences_in_range(
    repeat_mode: str | None,
    anchor: datetime,
    range_start: date,
    range_end: date,
) -> list[date]:
    """Todas las fechas concretas en las que esta tarea cae dentro de
    [range_start, range_end]. A diferencia de compute_occurrence_in_range
    (a lo sumo una, pensada para rangos de hasta 7 dias), esta soporta
    rangos arbitrariamente largos (ej. un mes completo, donde una tarea
    WEEKLY puede caer varias veces)."""
    if repeat_mode is None:
        occurrence = anchor.date()
        return [occurrence] if range_start <= occurrence <= range_end else []

    if repeat_mode == "WEEKLY":
        offset = (anchor.isoweekday() - range_start.isoweekday()) % 7
        occurrences = []
        current = date.fromordinal(range_start.toordinal() + offset)
        while current <= range_end:
            occurrences.append(current)
            current = date.fromordinal(current.toordinal() + 7)
        return occurrences

    if repeat_mode == "MONTHLY":
        occurrences = [
            date(year, month, _clamp_day(year, month, anchor.day))
            for year, month in _months_in_range(range_start, range_end)
        ]
        return sorted(o for o in occurrences if range_start <= o <= range_end)

    if repeat_mode == "YEARLY":
        years = {year for year, _ in _months_in_range(range_start, range_end)}
        occurrences = [date(year, anchor.month, _clamp_day(year, anchor.month, anchor.day)) for year in years]
        return sorted(o for o in occurrences if range_start <= o <= range_end)

    raise ValueError(f"repeat_mode desconocido: {repeat_mode}")


def parse_excluded_dates(excluded_dates: str | None) -> set[date]:
    if not excluded_dates:
        return set()
    return {date.fromisoformat(d) for d in excluded_dates.split(",") if d}


def serialize_excluded_dates(dates: set[date]) -> str:
    return ",".join(d.isoformat() for d in sorted(dates))


def occurrence_in_range(cld_task: CldTask, range_start: date, range_end: date) -> datetime | None:
    """Fecha+hora concreta de la (a lo sumo una) ocurrencia de cld_task dentro
    de [range_start, range_end], o None si no cae en ese rango (o esa
    ocurrencia puntual fue excluida). Sirve tanto para un solo dia
    (range_start == range_end, vista diaria) como para una semana completa
    (vista semanal)."""
    anchor = cld_task.repeat_date or cld_task.scheduled_date
    occurrence = compute_occurrence_in_range(cld_task.repeat_mode, anchor, range_start, range_end)
    if occurrence is None or occurrence in parse_excluded_dates(cld_task.excluded_dates):
        return None
    return datetime.combine(occurrence, anchor.timetz())


def occurrences_in_range(cld_task: CldTask, range_start: date, range_end: date) -> list[datetime]:
    """Igual que occurrence_in_range, pero sin asumir a lo sumo una
    ocurrencia: sirve para rangos largos (ej. un mes completo) donde una
    tarea recurrente puede caer varias veces."""
    anchor = cld_task.repeat_date or cld_task.scheduled_date
    excluded = parse_excluded_dates(cld_task.excluded_dates)
    occurrences = compute_occurrences_in_range(cld_task.repeat_mode, anchor, range_start, range_end)
    return [datetime.combine(o, anchor.timetz()) for o in occurrences if o not in excluded]


def build_checklist_task(cld_task: CldTask, week_id: int, occurrence_date: date) -> ChecklistTask:
    return ChecklistTask(
        cl_week_id=week_id,
        name=cld_task.name,
        day_of_week=str(occurrence_date.isoweekday()),
        importance=cld_task.importance,
        category_id=cld_task.category_id,
        detail=cld_task.detail,
        status=TaskStatus.PENDING.value,
    )


def build_checklist_task_for_week(cld_task: CldTask, week: ChecklistWeek) -> ChecklistTask | None:
    """Materializa la ocurrencia de cld_task dentro de week como una fila de
    cl_tasks, o None si esta tarea no cae dentro del rango de esa semana (o
    esa ocurrencia puntual fue excluida, ver CldTaskService.delete_task)."""
    anchor = cld_task.repeat_date or cld_task.scheduled_date
    occurrence = compute_occurrence_in_range(
        cld_task.repeat_mode, anchor, week.first_day, week.last_day
    )
    if occurrence is None or occurrence in parse_excluded_dates(cld_task.excluded_dates):
        return None

    return build_checklist_task(cld_task, week.id, occurrence)
