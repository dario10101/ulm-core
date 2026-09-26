"""Rutas de registros de comida. Solo hablan con MealService (nunca con el
repository ni con la sesion de base de datos directamente)."""

from datetime import date
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_timezone, get_current_user_id, get_meal_service
from app.schemas.meal import MealCreate, MealPage, MealRead, MealUpdate
from app.services.errors import MealNotFoundError
from app.services.meal_service import MealService

router = APIRouter(prefix="/meals", tags=["meals"])


@router.post("/", response_model=MealRead, status_code=201)
def create_meal(
    payload: MealCreate,
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    service: MealService = Depends(get_meal_service),
) -> MealRead:
    return service.create_meal(
        user_id=user_id,
        tz=tz,
        recorded_on=payload.recorded_on,
        meal_type=payload.meal_type.value,
        meal_size=payload.meal_size,
        components=payload.components,
        drink=payload.drink,
        note=payload.note,
    )


@router.get("/", response_model=MealPage)
def list_meals(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    service: MealService = Depends(get_meal_service),
) -> MealPage:
    items, total, total_pages = service.list_meals(
        user_id=user_id,
        tz=tz,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return MealPage(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.put("/{meal_id}", response_model=MealRead)
def update_meal(
    meal_id: int,
    payload: MealUpdate,
    user_id: int = Depends(get_current_user_id),
    tz: ZoneInfo = Depends(get_current_timezone),
    service: MealService = Depends(get_meal_service),
) -> MealRead:
    try:
        return service.update_meal(
            meal_id,
            user_id=user_id,
            tz=tz,
            recorded_on=payload.recorded_on,
            meal_type=payload.meal_type.value,
            meal_size=payload.meal_size,
            components=payload.components,
            drink=payload.drink,
            note=payload.note,
        )
    except MealNotFoundError:
        raise HTTPException(status_code=404, detail="Registro de comida no encontrado")


@router.delete("/{meal_id}", status_code=204)
def delete_meal(
    meal_id: int,
    user_id: int = Depends(get_current_user_id),
    service: MealService = Depends(get_meal_service),
) -> None:
    try:
        service.delete_meal(meal_id, user_id=user_id)
    except MealNotFoundError:
        raise HTTPException(status_code=404, detail="Registro de comida no encontrado")
