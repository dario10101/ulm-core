"""Rutas de checklists: categorias, template semanal, y semanas/tareas
concretas. Solo hablan con la capa de Service (nunca con el repository ni con
la sesion de base de datos directamente)."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    get_category_service,
    get_checklist_task_service,
    get_template_task_service,
    get_week_service,
)
from app.core.config import settings
from app.db.models.checklist import ChecklistTask, ChecklistTemplateTask
from app.schemas.checklist import (
    POINTS_BY_IMPORTANCE,
    CategoriesReplace,
    CategoryRead,
    Importance,
    TaskRead,
    TaskStatus,
    TaskStatusUpdate,
    TemplateTaskCreate,
    TemplateTaskRead,
    TemplateTaskUpdate,
    WeekCreate,
    WeekRead,
)
from app.services.category_service import (
    CategoryInUseError,
    CategoryNotFoundError as UnknownCategoryIdsError,
    CategoryService,
)
from app.services.checklist_task_service import (
    ChecklistTaskService,
    TaskNotFoundError as ChecklistTaskNotFoundError,
    WeekClosedError,
)
from app.services.template_task_service import (
    CategoryNotFoundError,
    TemplateTaskNotFoundError,
    TemplateTaskService,
)
from app.services.week_service import (
    InvalidWeekRangeError,
    WeekAlreadyClosedError,
    WeekAlreadyOpenError,
    WeekNotFoundError,
    WeekService,
)

router = APIRouter(prefix="/checklists", tags=["checklists"])


def _template_task_to_read(task: ChecklistTemplateTask) -> TemplateTaskRead:
    importance = Importance(task.importance)
    days = sorted(int(day) for day in task.day_of_week.split(",") if day)
    return TemplateTaskRead(
        id=task.id,
        name=task.name,
        importance=importance,
        points=POINTS_BY_IMPORTANCE[importance],
        category_id=task.category_id,
        days=days,
    )


def _checklist_task_to_read(task: ChecklistTask) -> TaskRead:
    importance = Importance(task.importance)
    return TaskRead(
        id=task.id,
        name=task.name,
        importance=importance,
        points=POINTS_BY_IMPORTANCE[importance],
        category_id=task.category_id,
        day_of_week=int(task.day_of_week),
        status=TaskStatus(task.status),
        last_modified_date=task.last_modified_date,
    )


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(service: CategoryService = Depends(get_category_service)) -> list[CategoryRead]:
    categories = service.list_categories(settings.default_user_id)
    return [CategoryRead.model_validate(category, from_attributes=True) for category in categories]


@router.put("/categories", response_model=list[CategoryRead])
def replace_categories(
    payload: CategoriesReplace, service: CategoryService = Depends(get_category_service)
) -> list[CategoryRead]:
    try:
        categories = service.replace_categories(settings.default_user_id, payload.items)
    except UnknownCategoryIdsError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Categorias inexistentes: {sorted(exc.category_ids)}",
        )
    except CategoryInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"No se pueden eliminar categorias con tareas asignadas: {', '.join(exc.category_names)}",
        )
    return [CategoryRead.model_validate(category, from_attributes=True) for category in categories]


@router.get("/template/tasks", response_model=list[TemplateTaskRead])
def list_template_tasks(
    service: TemplateTaskService = Depends(get_template_task_service),
) -> list[TemplateTaskRead]:
    tasks = service.list_tasks(settings.default_user_id)
    return [_template_task_to_read(task) for task in tasks]


@router.post("/template/tasks", response_model=TemplateTaskRead, status_code=201)
def create_template_task(
    payload: TemplateTaskCreate, service: TemplateTaskService = Depends(get_template_task_service)
) -> TemplateTaskRead:
    try:
        task = service.create_task(
            user_id=settings.default_user_id,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
            days=payload.days,
        )
    except CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    return _template_task_to_read(task)


@router.put("/template/tasks/{task_id}", response_model=TemplateTaskRead)
def update_template_task(
    task_id: int,
    payload: TemplateTaskUpdate,
    day: int = Query(ge=1, le=7, description="Dia (1-7) que se esta editando"),
    service: TemplateTaskService = Depends(get_template_task_service),
) -> TemplateTaskRead:
    try:
        task = service.update_task_for_day(
            task_id,
            day,
            user_id=settings.default_user_id,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
        )
    except TemplateTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada para ese dia")
    except CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    return _template_task_to_read(task)


@router.delete("/template/tasks/{task_id}", status_code=204)
def delete_template_task(
    task_id: int,
    day: int = Query(ge=1, le=7, description="Dia (1-7) que se esta eliminando"),
    service: TemplateTaskService = Depends(get_template_task_service),
) -> None:
    try:
        service.delete_task_for_day(task_id, day, user_id=settings.default_user_id)
    except TemplateTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada para ese dia")


# --- Semanas y tareas concretas ---


@router.get("/weeks/current", response_model=WeekRead | None)
def get_current_week(service: WeekService = Depends(get_week_service)) -> WeekRead | None:
    week = service.get_current_week(settings.default_user_id)
    if week is None:
        return None
    return WeekRead.model_validate(week, from_attributes=True)


@router.post("/weeks", response_model=WeekRead, status_code=201)
def create_week(payload: WeekCreate, service: WeekService = Depends(get_week_service)) -> WeekRead:
    try:
        week = service.create_week(settings.default_user_id, payload.first_day, payload.last_day)
    except InvalidWeekRangeError:
        raise HTTPException(status_code=422, detail="El rango debe cubrir exactamente 7 dias")
    except WeekAlreadyOpenError:
        raise HTTPException(status_code=409, detail="Ya hay una semana sin cerrar")
    return WeekRead.model_validate(week, from_attributes=True)


@router.post("/weeks/{week_id}/close", response_model=WeekRead)
def close_week(week_id: int, service: WeekService = Depends(get_week_service)) -> WeekRead:
    try:
        week = service.close_week(settings.default_user_id, week_id)
    except WeekNotFoundError:
        raise HTTPException(status_code=404, detail="Semana no encontrada")
    except WeekAlreadyClosedError:
        raise HTTPException(status_code=409, detail="La semana ya esta cerrada")
    return WeekRead.model_validate(week, from_attributes=True)


@router.get("/weeks/{week_id}/tasks", response_model=list[TaskRead])
def list_week_tasks(
    week_id: int, service: ChecklistTaskService = Depends(get_checklist_task_service)
) -> list[TaskRead]:
    try:
        tasks = service.list_tasks_for_week(settings.default_user_id, week_id)
    except WeekNotFoundError:
        raise HTTPException(status_code=404, detail="Semana no encontrada")
    return [_checklist_task_to_read(task) for task in tasks]


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task_status(
    task_id: int,
    payload: TaskStatusUpdate,
    service: ChecklistTaskService = Depends(get_checklist_task_service),
) -> TaskRead:
    try:
        task = service.update_status(settings.default_user_id, task_id, payload.status)
    except ChecklistTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    except WeekClosedError:
        raise HTTPException(
            status_code=409, detail="La semana ya esta cerrada, no se puede modificar"
        )
    return _checklist_task_to_read(task)
