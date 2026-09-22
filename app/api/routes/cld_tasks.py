"""Rutas de tareas de calendario (cld_tasks). Solo hablan con la capa de
Service (nunca con el repository ni con la sesion de base de datos)."""

from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_cld_task_service, get_current_timezone, get_current_user_id
from app.db.models.cld_task import CldTask
from app.schemas.checklist import Importance
from app.schemas.cld_task import (
    CldTaskChecklistSyncRead,
    CldTaskCreate,
    CldTaskOccurrenceRead,
    CldTaskRead,
    CldTaskUpdate,
    RepeatMode,
)
from app.services.cld_task_sync import to_local
from app.services.cld_task_service import (
    CategoryNotFoundError,
    CldTaskNotFoundError,
    CldTaskService,
    InvalidTaskDateError,
)

router = APIRouter(prefix="/calendar-tasks", tags=["calendar-tasks"])


def _cld_task_to_read(task: CldTask, tz: ZoneInfo) -> CldTaskRead:
    """Los anclajes salen en hora de pared del usuario, igual que entran: la
    BD guarda UTC, pero el contrato de la API es simetrico (el formulario de
    edicion del front parte de estos valores)."""
    return CldTaskRead(
        id=task.id,
        name=task.name,
        importance=Importance(task.importance),
        category_id=task.category_id,
        notify=task.notify,
        repeat_mode=RepeatMode(task.repeat_mode) if task.repeat_mode else None,
        scheduled_date=to_local(task.scheduled_date, tz) if task.scheduled_date else None,
        repeat_date=to_local(task.repeat_date, tz) if task.repeat_date else None,
        duration_minutes=task.duration_minutes,
        add_to_checklist=task.add_to_checklist,
        detail=task.detail,
        last_modified_date=task.last_modified_date,
    )


@router.get("", response_model=list[CldTaskOccurrenceRead])
def list_cld_tasks(
    date_: date | None = Query(default=None, alias="date"),
    first_day: date | None = Query(default=None),
    last_day: date | None = Query(default=None),
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    service: CldTaskService = Depends(get_cld_task_service),
) -> list[CldTaskOccurrenceRead]:
    """Ocurrencias para un dia puntual (`date`, vista diaria) o para un rango
    (`first_day`+`last_day`, vista semanal)."""
    if date_ is not None:
        occurrences = service.list_for_range(user_id, date_, date_, tz)
    elif first_day is not None and last_day is not None:
        occurrences = service.list_for_range(user_id, first_day, last_day, tz)
    else:
        raise HTTPException(status_code=422, detail="Se requiere 'date' o 'first_day' y 'last_day'")
    return [
        CldTaskOccurrenceRead(
            id=task.id,
            name=task.name,
            importance=Importance(task.importance),
            category_id=task.category_id,
            notify=task.notify,
            repeat_mode=RepeatMode(task.repeat_mode) if task.repeat_mode else None,
            scheduled_date=to_local(task.scheduled_date, tz) if task.scheduled_date else None,
            repeat_date=to_local(task.repeat_date, tz) if task.repeat_date else None,
            duration_minutes=task.duration_minutes,
            add_to_checklist=task.add_to_checklist,
            detail=task.detail,
            occurrence_at=occurrence.at_utc,
            occurrence_local=occurrence.local,
        )
        for task, occurrence in occurrences
    ]


@router.post("", response_model=CldTaskRead, status_code=201)
def create_cld_task(
    payload: CldTaskCreate,
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    service: CldTaskService = Depends(get_cld_task_service),
) -> CldTaskRead:
    try:
        task = service.create_task(
            user_id,
            tz,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
            notify=payload.notify,
            repeat_mode=payload.repeat_mode,
            scheduled_date=payload.scheduled_date,
            repeat_date=payload.repeat_date,
            duration_minutes=payload.duration_minutes,
            add_to_checklist=payload.add_to_checklist,
            detail=payload.detail,
        )
    except CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    return _cld_task_to_read(task, tz)


@router.put("/{task_id}", response_model=CldTaskRead)
def update_cld_task(
    task_id: int,
    payload: CldTaskUpdate,
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    service: CldTaskService = Depends(get_cld_task_service),
) -> CldTaskRead:
    try:
        task = service.update_task(
            user_id,
            task_id,
            tz,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
            notify=payload.notify,
            detail=payload.detail,
            scheduled_date=payload.scheduled_date,
            repeat_date=payload.repeat_date,
            duration_minutes=payload.duration_minutes,
        )
    except CldTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    except CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    except InvalidTaskDateError:
        raise HTTPException(
            status_code=422,
            detail="La fecha enviada no corresponde al modo de repeticion de la tarea",
        )
    return _cld_task_to_read(task, tz)


@router.delete("/{task_id}", status_code=204)
def delete_cld_task(
    task_id: int,
    occurrence_date: date | None = Query(default=None),
    user_id: int = Depends(get_current_user_id),
    service: CldTaskService = Depends(get_cld_task_service),
) -> None:
    try:
        service.delete_task(user_id, task_id, occurrence_date)
    except CldTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")


@router.post("/{task_id}/checklist", response_model=CldTaskChecklistSyncRead)
def enable_cld_task_checklist_sync(
    task_id: int,
    occurrence_date: date = Query(),
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    service: CldTaskService = Depends(get_cld_task_service),
) -> CldTaskChecklistSyncRead:
    try:
        task, added = service.enable_checklist_sync(user_id, task_id, occurrence_date)
    except CldTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    return CldTaskChecklistSyncRead(task=_cld_task_to_read(task, tz), added_to_current_week=added)
