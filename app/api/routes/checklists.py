"""Rutas de checklists: categorias, template semanal, y semanas/tareas
concretas. Solo hablan con la capa de Service (nunca con el repository ni con
la sesion de base de datos directamente)."""

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    get_category_service,
    get_checklist_analytics_service,
    get_checklist_task_service,
    get_template_task_service,
    get_week_service,
)
from app.core.config import settings
from app.db.models.checklist import ChecklistTask, ChecklistTemplateTask
from app.schemas.checklist import (
    POINTS_BY_IMPORTANCE,
    AnalyticsCategory,
    CategoriesReplace,
    CategoryRead,
    Importance,
    MonthlyAnalyticsPoint,
    MonthlyAnalyticsRead,
    TaskCreate,
    TaskRead,
    TaskStatus,
    TaskStatusUpdate,
    TaskUpdate,
    TemplateTaskCreate,
    TemplateTaskRead,
    TemplateTaskUpdate,
    WeeklyAnalyticsPoint,
    WeeklyAnalyticsRead,
    WeekCreate,
    WeekRangeRead,
    WeekRead,
)
from app.services.category_service import (
    CategoryInUseError,
    CategoryNotFoundError as UnknownCategoryIdsError,
    CategoryService,
)
from app.services.checklist_analytics_service import ChecklistAnalyticsService
from app.services.checklist_task_service import (
    CategoryNotFoundError as TaskCategoryNotFoundError,
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
    WeekEndInThePastError,
    WeekHasPendingTasksError,
    WeekNotFoundError,
    WeekStartTooEarlyError,
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
        detail=task.detail,
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
        detail=task.detail,
    )


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    include_disabled: bool = False,
    service: CategoryService = Depends(get_category_service),
) -> list[CategoryRead]:
    categories = service.list_categories(settings.default_user_id, include_disabled=include_disabled)
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


@router.post("/categories/{category_id}/enable", response_model=CategoryRead)
def enable_category(
    category_id: int, service: CategoryService = Depends(get_category_service)
) -> CategoryRead:
    try:
        category = service.enable_category(settings.default_user_id, category_id)
    except UnknownCategoryIdsError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Categorias inexistentes: {sorted(exc.category_ids)}",
        )
    return CategoryRead.model_validate(category, from_attributes=True)


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
            detail=payload.detail,
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
            detail=payload.detail,
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


@router.get("/weeks/next-range", response_model=WeekRangeRead)
def get_next_week_range(service: WeekService = Depends(get_week_service)) -> WeekRangeRead:
    min_first_day, min_last_day = service.get_next_range(settings.default_user_id)
    return WeekRangeRead(min_first_day=min_first_day, min_last_day=min_last_day)


@router.post("/weeks", response_model=WeekRead, status_code=201)
def create_week(payload: WeekCreate, service: WeekService = Depends(get_week_service)) -> WeekRead:
    try:
        week = service.create_week(settings.default_user_id, payload.first_day, payload.last_day)
    except InvalidWeekRangeError:
        raise HTTPException(status_code=422, detail="El rango debe cubrir entre 1 y 7 dias")
    except WeekAlreadyOpenError:
        raise HTTPException(status_code=409, detail="Ya hay una semana sin cerrar")
    except WeekEndInThePastError:
        raise HTTPException(status_code=422, detail="El ultimo dia no puede ser anterior a hoy")
    except WeekStartTooEarlyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"El primer dia no puede ser anterior a {exc.min_first_day.isoformat()}",
        )
    return WeekRead.model_validate(week, from_attributes=True)


@router.post("/weeks/{week_id}/close", response_model=WeekRead)
def close_week(week_id: int, service: WeekService = Depends(get_week_service)) -> WeekRead:
    try:
        week = service.close_week(settings.default_user_id, week_id)
    except WeekNotFoundError:
        raise HTTPException(status_code=404, detail="Semana no encontrada")
    except WeekAlreadyClosedError:
        raise HTTPException(status_code=409, detail="La semana ya esta cerrada")
    except WeekHasPendingTasksError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Todavia hay {exc.pending_count} tarea(s) sin marcar (PENDING)",
        )
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


@router.post("/weeks/{week_id}/tasks", response_model=TaskRead, status_code=201)
def create_week_task(
    week_id: int,
    payload: TaskCreate,
    service: ChecklistTaskService = Depends(get_checklist_task_service),
) -> TaskRead:
    """Tarea circunstancial agregada directamente a la semana en curso, sin
    pasar por (ni modificar) el template."""
    try:
        task = service.create_task(
            settings.default_user_id,
            week_id,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
            day_of_week=payload.day_of_week,
            detail=payload.detail,
        )
    except WeekNotFoundError:
        raise HTTPException(status_code=404, detail="Semana no encontrada")
    except WeekClosedError:
        raise HTTPException(
            status_code=409, detail="La semana ya esta cerrada, no se pueden agregar tareas"
        )
    except TaskCategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    return _checklist_task_to_read(task)


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


@router.put("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    service: ChecklistTaskService = Depends(get_checklist_task_service),
) -> TaskRead:
    """Edicion (modo Edit del checklist): mismo dia y semana, cambia nombre,
    importancia y/o categoria."""
    try:
        task = service.update_task(
            settings.default_user_id,
            task_id,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
            detail=payload.detail,
        )
    except ChecklistTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    except WeekClosedError:
        raise HTTPException(
            status_code=409, detail="La semana ya esta cerrada, no se puede modificar"
        )
    except TaskCategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")
    return _checklist_task_to_read(task)


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int, service: ChecklistTaskService = Depends(get_checklist_task_service)
) -> None:
    try:
        service.delete_task(settings.default_user_id, task_id)
    except ChecklistTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    except WeekClosedError:
        raise HTTPException(
            status_code=409, detail="La semana ya esta cerrada, no se puede eliminar"
        )


# --- Analytics (tendencias de semanas cerradas) ---


@router.get("/analytics/weekly", response_model=WeeklyAnalyticsRead)
def get_weekly_analytics(
    year: int = Query(ge=2000, le=2100),
    service: ChecklistAnalyticsService = Depends(get_checklist_analytics_service),
) -> WeeklyAnalyticsRead:
    categories, weeks = service.get_weekly(settings.default_user_id, year)
    return WeeklyAnalyticsRead(
        year=year,
        categories=[AnalyticsCategory(category_id=cid, name=name) for cid, name in categories],
        weeks=[WeeklyAnalyticsPoint(**week) for week in weeks],
    )


@router.get("/analytics/monthly", response_model=MonthlyAnalyticsRead)
def get_monthly_analytics(
    year: int = Query(ge=2000, le=2100),
    service: ChecklistAnalyticsService = Depends(get_checklist_analytics_service),
) -> MonthlyAnalyticsRead:
    categories, months = service.get_monthly(settings.default_user_id, year)
    return MonthlyAnalyticsRead(
        year=year,
        categories=[AnalyticsCategory(category_id=cid, name=name) for cid, name in categories],
        months=[MonthlyAnalyticsPoint(**month) for month in months],
    )
