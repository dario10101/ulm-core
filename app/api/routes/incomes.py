"""Rutas de registros de ingreso (directos e intereses) y de sus catalogos.
Solo hablan con IncomeService (nunca con el repository ni con la sesion)."""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user_id, get_income_service, get_income_summary_service
from app.repositories.income_repository import IncomeFilters
from app.repositories.income_summary_repository import IncomeSummaryFilters
from app.schemas.finance import (
    DirectIncomeCreate,
    DirectIncomePage,
    DirectIncomeRead,
    DirectIncomeUpdate,
    IncomeKindFilter,
    IncomeOptionsRead,
    IncomeStackBy,
    IncomeSummaryGroupBy,
    IncomeSummaryRead,
    InterestIncomeCreate,
    InterestIncomePage,
    InterestIncomeRead,
    InterestIncomeUpdate,
)
from app.services.errors import (
    IncomeNotFoundError,
    IncomeSourceNotFoundError,
    IncomeSubcategoryNotFoundError,
    InterestPeriodTakenError,
    TagNotFoundError,
)
from app.services.income_service import IncomeService, build_filters
from app.services.income_summary_service import IncomeSummaryService

router = APIRouter(prefix="/incomes", tags=["incomes"])

_REFERENCE_ERRORS = (IncomeSourceNotFoundError, IncomeSubcategoryNotFoundError, TagNotFoundError)
_NOT_FOUND_DETAIL = "Registro de ingreso no encontrado"


def income_filters(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source_id: int | None = Query(default=None),
    subcategory_id: int | None = Query(default=None),
    tag_ids: list[int] | None = Query(default=None),
    # Sin ge=0: el interes de un mes puede ser negativo y filtrarse como tal.
    min_amount: float | None = Query(default=None),
    max_amount: float | None = Query(default=None),
) -> IncomeFilters:
    """Mismos filtros para ambos listados (dependencia comun de FastAPI)."""
    return build_filters(
        start_date=start_date,
        end_date=end_date,
        source_id=source_id,
        subcategory_id=subcategory_id,
        tag_ids=tag_ids,
        min_amount=min_amount,
        max_amount=max_amount,
    )


@router.get("/options", response_model=IncomeOptionsRead)
def get_income_options(
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> IncomeOptionsRead:
    return service.get_options(user_id=user_id)


@router.get("/summary", response_model=IncomeSummaryRead)
def summarize_incomes(
    group_by: IncomeSummaryGroupBy = Query(),
    stack_by: IncomeStackBy | None = Query(
        default=None, description="Desglose por periodo (solo month/year)"
    ),
    kind: IncomeKindFilter | None = Query(default=None, description="Sin valor: ambos"),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    source_ids: list[int] | None = Query(default=None),
    subcategory_ids: list[int] | None = Query(default=None),
    tag_ids: list[int] | None = Query(default=None),
    user_id: int = Depends(get_current_user_id),
    service: IncomeSummaryService = Depends(get_income_summary_service),
) -> IncomeSummaryRead:
    """Agregado de directos + intereses para graficos. Multi-seleccion en
    fuentes/subcategorias/tags: coincide cualquiera de los ids."""
    return service.summarize(
        user_id=user_id,
        group_by=group_by,
        stack_by=stack_by,
        filters=IncomeSummaryFilters(
            kind=kind.value if kind else None,
            start_date=start_date,
            end_date=end_date,
            source_ids=tuple(source_ids or ()),
            subcategory_ids=tuple(subcategory_ids or ()),
            tag_ids=tuple(tag_ids or ()),
        ),
    )


# --- Directos ---


@router.post("/direct", response_model=DirectIncomeRead, status_code=201)
def create_direct_income(
    payload: DirectIncomeCreate,
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> DirectIncomeRead:
    try:
        return service.create_direct(user_id=user_id, payload=payload)
    except _REFERENCE_ERRORS as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/direct", response_model=DirectIncomePage)
def list_direct_incomes(
    filters: IncomeFilters = Depends(income_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> DirectIncomePage:
    items, total, total_pages = service.list_direct(
        user_id=user_id, filters=filters, page=page, page_size=page_size
    )
    return DirectIncomePage(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.put("/direct/{record_id}", response_model=DirectIncomeRead)
def update_direct_income(
    record_id: int,
    payload: DirectIncomeUpdate,
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> DirectIncomeRead:
    try:
        return service.update_direct(record_id, user_id=user_id, payload=payload)
    except IncomeNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    except _REFERENCE_ERRORS as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/direct/{record_id}", status_code=204)
def delete_direct_income(
    record_id: int,
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> None:
    try:
        service.delete_direct(record_id, user_id=user_id)
    except IncomeNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)


# --- Intereses ---


@router.post("/interest", response_model=InterestIncomeRead, status_code=201)
def create_interest_income(
    payload: InterestIncomeCreate,
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> InterestIncomeRead:
    try:
        return service.create_interest(user_id=user_id, payload=payload)
    except _REFERENCE_ERRORS as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InterestPeriodTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("/interest", response_model=InterestIncomePage)
def list_interest_incomes(
    filters: IncomeFilters = Depends(income_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> InterestIncomePage:
    items, total, total_pages = service.list_interest(
        user_id=user_id, filters=filters, page=page, page_size=page_size
    )
    return InterestIncomePage(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.put("/interest/{record_id}", response_model=InterestIncomeRead)
def update_interest_income(
    record_id: int,
    payload: InterestIncomeUpdate,
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> InterestIncomeRead:
    try:
        return service.update_interest(record_id, user_id=user_id, payload=payload)
    except IncomeNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    except _REFERENCE_ERRORS as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except InterestPeriodTakenError as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.delete("/interest/{record_id}", status_code=204)
def delete_interest_income(
    record_id: int,
    user_id: int = Depends(get_current_user_id),
    service: IncomeService = Depends(get_income_service),
) -> None:
    try:
        service.delete_interest(record_id, user_id=user_id)
    except IncomeNotFoundError:
        raise HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
