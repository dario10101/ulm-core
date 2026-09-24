"""Rutas de checklists: categorias, template semanal, y semanas/tareas
concretas. Solo hablan con la capa de Service (nunca con el repository ni con
la sesion de base de datos directamente)."""

from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import (
    get_category_service,
    get_checklist_analytics_service,
    get_checklist_task_service,
    get_current_timezone,
    get_current_user_id,
    get_template_task_service,
    get_week_service,
)
from app.schemas.checklist import (
    AnalyticsCategory,
    CategoriesReplace,
    CategoryRead,
    MonthlyAnalyticsPoint,
    MonthlyAnalyticsRead,
    TaskCreate,
    TaskRead,
    TaskStatusUpdate,
    TaskUpdate,
    TemplateTaskCreate,
    TemplateTaskRead,
    TemplateTaskUpdate,
    WeekCreate,
    WeeklyAnalyticsPoint,
    WeeklyAnalyticsRead,
    WeekRangeRead,
    WeekRead,
)
from app.services.category_service import CategoryService
from app.services.checklist_analytics_service import ChecklistAnalyticsService
from app.services.checklist_task_service import ChecklistTaskService
from app.services.errors import (
    CategoryInUseError,
    CategoryNotFoundError,
    InvalidWeekRangeError,
    TaskNotFoundError,
    TemplateTaskNotFoundError,
    WeekAlreadyClosedError,
    WeekAlreadyOpenError,
    WeekClosedError,
    WeekEndInThePastError,
    WeekHasPendingTasksError,
    WeekNotFoundError,
    WeekStartTooEarlyError,
)
from app.services.template_task_service import TemplateTaskService
from app.services.week_service import WeekService

router = APIRouter(prefix="/checklists", tags=["checklists"])


@router.get("/categories", response_model=list[CategoryRead])
def list_categories(
    include_disabled: bool = False,
    user_id: int = Depends(get_current_user_id),
    service: CategoryService = Depends(get_category_service),
) -> list[CategoryRead]:
    return service.list_categories(user_id, include_disabled=include_disabled)


@router.put("/categories", response_model=list[CategoryRead])
def replace_categories(
    payload: CategoriesReplace,
    user_id: int = Depends(get_current_user_id),
    service: CategoryService = Depends(get_category_service),
) -> list[CategoryRead]:
    try:
        return service.replace_categories(user_id, payload.items)
    except CategoryNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Categorias inexistentes: {sorted(exc.category_ids)}",
        )
    except CategoryInUseError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "No se pueden eliminar categorias con tareas asignadas: "
                f"{', '.join(exc.category_names)}"
            ),
        )


@router.post("/categories/{category_id}/enable", response_model=CategoryRead)
def enable_category(
    category_id: int,
    user_id: int = Depends(get_current_user_id),
    service: CategoryService = Depends(get_category_service),
) -> CategoryRead:
    try:
        return service.enable_category(user_id, category_id)
    except CategoryNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Categorias inexistentes: {sorted(exc.category_ids)}",
        )


@router.get("/template/tasks", response_model=list[TemplateTaskRead])
def list_template_tasks(
    user_id: int = Depends(get_current_user_id),
    service: TemplateTaskService = Depends(get_template_task_service),
) -> list[TemplateTaskRead]:
    return service.list_tasks(user_id)


@router.post("/template/tasks", response_model=TemplateTaskRead, status_code=201)
def create_template_task(
    payload: TemplateTaskCreate,
    user_id: int = Depends(get_current_user_id),
    service: TemplateTaskService = Depends(get_template_task_service),
) -> TemplateTaskRead:
    try:
        return service.create_task(
            user_id=user_id,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
            days=payload.days,
            detail=payload.detail,
        )
    except CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")


@router.put("/template/tasks/{task_id}", response_model=TemplateTaskRead)
def update_template_task(
    task_id: int,
    payload: TemplateTaskUpdate,
    day: int = Query(ge=1, le=7, description="Dia (1-7) que se esta editando"),
    user_id: int = Depends(get_current_user_id),
    service: TemplateTaskService = Depends(get_template_task_service),
) -> TemplateTaskRead:
    try:
        return service.update_task_for_day(
            task_id,
            day,
            user_id=user_id,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
            detail=payload.detail,
        )
    except TemplateTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada para ese dia")
    except CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")


@router.delete("/template/tasks/{task_id}", status_code=204)
def delete_template_task(
    task_id: int,
    day: int = Query(ge=1, le=7, description="Dia (1-7) que se esta eliminando"),
    user_id: int = Depends(get_current_user_id),
    service: TemplateTaskService = Depends(get_template_task_service),
) -> None:
    try:
        service.delete_task_for_day(task_id, day, user_id=user_id)
    except TemplateTaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada para ese dia")


# --- Semanas y tareas concretas ---


@router.get("/weeks/current", response_model=WeekRead | None)
def get_current_week(
    user_id: int = Depends(get_current_user_id), service: WeekService = Depends(get_week_service)
) -> WeekRead | None:
    return service.get_current_week(user_id)


@router.get("/weeks/next-range", response_model=WeekRangeRead)
def get_next_week_range(
    user_id: int = Depends(get_current_user_id), service: WeekService = Depends(get_week_service)
) -> WeekRangeRead:
    min_first_day, min_last_day = service.get_next_range(user_id)
    return WeekRangeRead(min_first_day=min_first_day, min_last_day=min_last_day)


@router.post("/weeks", response_model=WeekRead, status_code=201)
def create_week(
    payload: WeekCreate,
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    service: WeekService = Depends(get_week_service),
) -> WeekRead:
    try:
        return service.create_week(user_id, payload.first_day, payload.last_day, tz)
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


@router.post("/weeks/{week_id}/close", response_model=WeekRead)
def close_week(
    week_id: int,
    user_id: int = Depends(get_current_user_id),
    service: WeekService = Depends(get_week_service),
) -> WeekRead:
    try:
        return service.close_week(user_id, week_id)
    except WeekNotFoundError:
        raise HTTPException(status_code=404, detail="Semana no encontrada")
    except WeekAlreadyClosedError:
        raise HTTPException(status_code=409, detail="La semana ya esta cerrada")
    except WeekHasPendingTasksError as exc:
        raise HTTPException(
            status_code=409,
            detail=f"Todavia hay {exc.pending_count} tarea(s) sin marcar (PENDING)",
        )


@router.get("/weeks/{week_id}/tasks", response_model=list[TaskRead])
def list_week_tasks(
    week_id: int,
    user_id: int = Depends(get_current_user_id),
    service: ChecklistTaskService = Depends(get_checklist_task_service),
) -> list[TaskRead]:
    try:
        return service.list_tasks_for_week(user_id, week_id)
    except WeekNotFoundError:
        raise HTTPException(status_code=404, detail="Semana no encontrada")


@router.post("/weeks/{week_id}/tasks", response_model=TaskRead, status_code=201)
def create_week_task(
    week_id: int,
    payload: TaskCreate,
    user_id: int = Depends(get_current_user_id),
    service: ChecklistTaskService = Depends(get_checklist_task_service),
) -> TaskRead:
    """Tarea circunstancial agregada directamente a la semana en curso, sin
    pasar por (ni modificar) el template."""
    try:
        return service.create_task(
            user_id,
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
    except CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")


@router.patch("/tasks/{task_id}", response_model=TaskRead)
def update_task_status(
    task_id: int,
    payload: TaskStatusUpdate,
    user_id: int = Depends(get_current_user_id),
    service: ChecklistTaskService = Depends(get_checklist_task_service),
) -> TaskRead:
    try:
        return service.update_status(user_id, task_id, payload.status)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    except WeekClosedError:
        raise HTTPException(
            status_code=409, detail="La semana ya esta cerrada, no se puede modificar"
        )


@router.put("/tasks/{task_id}", response_model=TaskRead)
def update_task(
    task_id: int,
    payload: TaskUpdate,
    user_id: int = Depends(get_current_user_id),
    service: ChecklistTaskService = Depends(get_checklist_task_service),
) -> TaskRead:
    """Edicion (modo Edit del checklist): mismo dia y semana, cambia nombre,
    importancia y/o categoria."""
    try:
        return service.update_task(
            user_id,
            task_id,
            name=payload.name,
            importance=payload.importance,
            category_id=payload.category_id,
            detail=payload.detail,
        )
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    except WeekClosedError:
        raise HTTPException(
            status_code=409, detail="La semana ya esta cerrada, no se puede modificar"
        )
    except CategoryNotFoundError:
        raise HTTPException(status_code=404, detail="Categoria no encontrada")


@router.delete("/tasks/{task_id}", status_code=204)
def delete_task(
    task_id: int,
    user_id: int = Depends(get_current_user_id),
    service: ChecklistTaskService = Depends(get_checklist_task_service),
) -> None:
    try:
        service.delete_task(user_id, task_id)
    except TaskNotFoundError:
        raise HTTPException(status_code=404, detail="Tarea no encontrada")
    except WeekClosedError:
        raise HTTPException(
            status_code=409, detail="La semana ya esta cerrada, no se puede eliminar"
        )


# --- Analytics (tendencias de semanas cerradas) ---


@router.get("/analytics/weekly", response_model=WeeklyAnalyticsRead)
def get_weekly_analytics(
    year: int = Query(ge=2000, le=2100),
    user_id: int = Depends(get_current_user_id),
    service: ChecklistAnalyticsService = Depends(get_checklist_analytics_service),
) -> WeeklyAnalyticsRead:
    categories, weeks = service.get_weekly(user_id, year)
    return WeeklyAnalyticsRead(
        year=year,
        categories=[AnalyticsCategory(category_id=cid, name=name) for cid, name in categories],
        weeks=[WeeklyAnalyticsPoint(**week) for week in weeks],
    )


@router.get("/analytics/monthly", response_model=MonthlyAnalyticsRead)
def get_monthly_analytics(
    year: int = Query(ge=2000, le=2100),
    user_id: int = Depends(get_current_user_id),
    service: ChecklistAnalyticsService = Depends(get_checklist_analytics_service),
) -> MonthlyAnalyticsRead:
    categories, months = service.get_monthly(user_id, year)
    return MonthlyAnalyticsRead(
        year=year,
        categories=[AnalyticsCategory(category_id=cid, name=name) for cid, name in categories],
        months=[MonthlyAnalyticsPoint(**month) for month in months],
    )
