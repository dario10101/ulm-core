"""Logica compartida para sincronizar tareas de calendario (cld_tasks) con el
checklist semanal (cl_tasks). Usada tanto al crear una tarea de calendario
(ChecklistTaskService no aplica aca) como al crear una semana nueva.

Zona horaria
------------
La BD guarda siempre UTC (`timestamptz`), pero un calendario razona sobre
fechas civiles: "que dia es", "que dia de la semana", "que dia del mes". Esas
dos cosas solo se pueden relacionar con una zona horaria explicita, asi que
toda funcion que calcula ocurrencias convierte primero el ancla a la zona del
usuario (`users.timezone`) y recien ahi hace las cuentas.

Las funciones `compute_*` son puras y esperan un ancla YA convertida a hora
local (naive). Las que reciben un `CldTask` hacen la conversion ellas mismas
y reciben la zona como parametro.
"""

from calendar import monthrange
from dataclasses import dataclass
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from app.db.models.checklist import ChecklistTask, ChecklistWeek
from app.db.models.cld_task import CldTask
from app.schemas.checklist import TaskStatus


@dataclass(frozen=True)
class Occurrence:
    """Una ocurrencia concreta de una tarea de calendario, en sus dos formas:
    el instante (para guardar/ordenar) y la hora de pared del usuario (para
    mostrar y para decidir a que dia del calendario pertenece)."""

    at_utc: datetime
    """Instante exacto, con tzinfo=UTC."""

    local: datetime
    """Hora de pared en la zona del usuario, sin tzinfo (ej. 2026-09-15 19:30)."""


def to_local(value: datetime, tz: ZoneInfo) -> datetime:
    """Instante -> hora de pared del usuario, sin tzinfo.

    Un datetime naive se interpreta como UTC, no como local: todo lo que sale
    de la BD esta en UTC, y SQLite (que usan los tests) devuelve estos valores
    sin tzinfo mientras que Postgres los devuelve con el. Asumir UTC en ambos
    casos hace que los dos motores se comporten igual."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(tz).replace(tzinfo=None)


def to_utc(local_value: datetime, tz: ZoneInfo) -> datetime:
    """Hora de pared del usuario -> instante UTC.

    Se le adjunta la zona IANA (no un offset fijo): asi el offset se resuelve
    para esa fecha puntual y sigue siendo correcto en zonas con horario de
    verano. En una hora ambigua (la que ocurre dos veces al atrasar el reloj)
    Python toma la primera por defecto (fold=0); en `America/Bogota` el caso
    no existe porque no hay horario de verano."""
    return local_value.replace(tzinfo=tz).astimezone(UTC)


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
    semana de checklist), por lo que a lo sumo hay una ocurrencia.

    `anchor` debe venir ya en hora local del usuario (ver to_local)."""
    if repeat_mode is None:
        occurrence = anchor.date()
        return occurrence if range_start <= occurrence <= range_end else None

    if repeat_mode == "WEEKLY":
        offset = (anchor.isoweekday() - range_start.isoweekday()) % 7
        occurrence = date.fromordinal(range_start.toordinal() + offset)
        return occurrence if occurrence <= range_end else None

    if repeat_mode == "MONTHLY":
        for year, month in {
            (range_start.year, range_start.month),
            (range_end.year, range_end.month),
        }:
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
    WEEKLY puede caer varias veces).

    `anchor` debe venir ya en hora local del usuario (ver to_local)."""
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
        occurrences = [
            date(year, anchor.month, _clamp_day(year, anchor.month, anchor.day)) for year in years
        ]
        return sorted(o for o in occurrences if range_start <= o <= range_end)

    raise ValueError(f"repeat_mode desconocido: {repeat_mode}")


def parse_excluded_dates(excluded_dates: str | None) -> set[date]:
    """Las fechas excluidas son dias locales del usuario, no dias UTC."""
    if not excluded_dates:
        return set()
    return {date.fromisoformat(d) for d in excluded_dates.split(",") if d}


def serialize_excluded_dates(dates: set[date]) -> str:
    return ",".join(d.isoformat() for d in sorted(dates))


def local_anchor_of(cld_task: CldTask, tz: ZoneInfo) -> datetime:
    """Ancla de la tarea (puntual o recurrente) en hora de pared del usuario."""
    return to_local(cld_task.repeat_date or cld_task.scheduled_date, tz)


def occurrences_in_range(
    cld_task: CldTask, range_start: date, range_end: date, tz: ZoneInfo
) -> list[Occurrence]:
    """Ocurrencias de cld_task dentro de [range_start, range_end], expresado
    en dias locales del usuario. Sirve para un solo dia (range_start ==
    range_end, vista diaria), para una semana, y para rangos largos como un
    mes completo (donde una tarea recurrente puede caer varias veces)."""
    anchor = local_anchor_of(cld_task, tz)
    excluded = parse_excluded_dates(cld_task.excluded_dates)
    dates = compute_occurrences_in_range(cld_task.repeat_mode, anchor, range_start, range_end)

    occurrences: list[Occurrence] = []
    for occurrence_date in dates:
        if occurrence_date in excluded:
            continue
        local = datetime.combine(occurrence_date, anchor.time())
        occurrences.append(Occurrence(at_utc=to_utc(local, tz), local=local))
    return occurrences


def build_checklist_task(cld_task: CldTask, week_id: int, occurrence_date: date) -> ChecklistTask:
    """`occurrence_date` es un dia local del usuario, asi que su isoweekday()
    es el dia de semana que el usuario efectivamente ve en el checklist."""
    return ChecklistTask(
        cl_week_id=week_id,
        name=cld_task.name,
        day_of_week=str(occurrence_date.isoweekday()),
        importance=cld_task.importance,
        category_id=cld_task.category_id,
        detail=cld_task.detail,
        status=TaskStatus.PENDING.value,
    )


def occurrence_date_in_week(cld_task: CldTask, week: ChecklistWeek, tz: ZoneInfo) -> date | None:
    """Dia local en que cld_task cae dentro de la semana, o None si no cae
    (o si esa ocurrencia puntual fue excluida, ver CldTaskService.delete_task)."""
    anchor = local_anchor_of(cld_task, tz)
    occurrence = compute_occurrence_in_range(
        cld_task.repeat_mode, anchor, week.first_day, week.last_day
    )
    if occurrence is None or occurrence in parse_excluded_dates(cld_task.excluded_dates):
        return None
    return occurrence


def build_checklist_task_for_week(
    cld_task: CldTask, week: ChecklistWeek, tz: ZoneInfo
) -> ChecklistTask | None:
    """Materializa la ocurrencia de cld_task dentro de week como una fila de
    cl_tasks, o None si esta tarea no cae dentro del rango de esa semana."""
    occurrence = occurrence_date_in_week(cld_task, week, tz)
    if occurrence is None:
        return None
    return build_checklist_task(cld_task, week.id, occurrence)
