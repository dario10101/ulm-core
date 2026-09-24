"""Rutas de registros de peso. Solo hablan con WeightService (nunca con el
repository ni con la sesion de base de datos directamente)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user_id, get_weight_service
from app.schemas.weight import WeightCreate, WeightPage, WeightRead, WeightUpdate
from app.services.errors import WeightNotFoundError
from app.services.weight_service import WeightService

router = APIRouter(prefix="/weights", tags=["weights"])


@router.post("/", response_model=WeightRead, status_code=201)
def create_weight(
    payload: WeightCreate,
    user_id: int = Depends(get_current_user_id),
    service: WeightService = Depends(get_weight_service),
) -> WeightRead:
    record = service.create_weight(
        user_id=user_id,
        weight_kg=Decimal(str(payload.weight_kg)),
        recorded_on=payload.recorded_on,
        note=payload.note,
    )
    return record


@router.get("/", response_model=WeightPage)
def list_weights(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    service: WeightService = Depends(get_weight_service),
) -> WeightPage:
    items, total, total_pages = service.list_weights(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return WeightPage(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.put("/{weight_id}", response_model=WeightRead)
def update_weight(
    weight_id: int,
    payload: WeightUpdate,
    user_id: int = Depends(get_current_user_id),
    service: WeightService = Depends(get_weight_service),
) -> WeightRead:
    try:
        return service.update_weight(
            weight_id,
            user_id=user_id,
            weight_kg=Decimal(str(payload.weight_kg)),
            recorded_on=payload.recorded_on,
            note=payload.note,
        )
    except WeightNotFoundError:
        raise HTTPException(status_code=404, detail="Registro de peso no encontrado")


@router.delete("/{weight_id}", status_code=204)
def delete_weight(
    weight_id: int,
    user_id: int = Depends(get_current_user_id),
    service: WeightService = Depends(get_weight_service),
) -> None:
    try:
        service.delete_weight(weight_id, user_id=user_id)
    except WeightNotFoundError:
        raise HTTPException(status_code=404, detail="Registro de peso no encontrado")
