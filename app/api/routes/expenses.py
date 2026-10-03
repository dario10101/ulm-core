"""Rutas de registros de gasto y de sus catalogos (categorias, metodos de
pago, tags). Solo hablan con ExpenseService/FinanceCatalogService (nunca con
el repository ni con la sesion de base de datos directamente)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user_id, get_expense_service, get_finance_catalog_service
from app.schemas.finance import (
    ExpenseCreate,
    ExpenseOptionsRead,
    ExpensePage,
    ExpenseRead,
    ExpenseSummaryGroupBy,
    ExpenseSummaryRead,
    ExpenseUpdate,
)
from app.services.errors import (
    ExpenseCategoryNotFoundError,
    ExpenseNotFoundError,
    PaymentMethodNotFoundError,
    TagNotFoundError,
)
from app.services.expense_service import ExpenseService
from app.services.finance_catalog_service import FinanceCatalogService

router = APIRouter(prefix="/expenses", tags=["expenses"])


@router.get("/options", response_model=ExpenseOptionsRead)
def get_expense_options(
    user_id: int = Depends(get_current_user_id),
    service: FinanceCatalogService = Depends(get_finance_catalog_service),
) -> ExpenseOptionsRead:
    return service.get_options(user_id=user_id)


@router.post("/", response_model=ExpenseRead, status_code=201)
def create_expense(
    payload: ExpenseCreate,
    user_id: int = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpenseRead:
    try:
        return service.create_expense(
            user_id=user_id,
            name=payload.name,
            amount=Decimal(str(payload.amount)),
            recorded_on=payload.recorded_on,
            note=payload.note,
            payment_method_id=payload.payment_method_id,
            category_id=payload.category_id,
            tag_ids=payload.tag_ids,
        )
    except (ExpenseCategoryNotFoundError, PaymentMethodNotFoundError, TagNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/", response_model=ExpensePage)
def list_expenses(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    # Multi-seleccion: coincide si el gasto tiene cualquiera de los ids.
    category_ids: list[int] | None = Query(default=None),
    payment_method_ids: list[int] | None = Query(default=None),
    tag_ids: list[int] | None = Query(default=None),
    min_amount: float | None = Query(default=None, ge=0),
    max_amount: float | None = Query(default=None, ge=0),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpensePage:
    items, total, total_pages = service.list_expenses(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        category_ids=category_ids,
        payment_method_ids=payment_method_ids,
        tag_ids=tag_ids,
        min_amount=Decimal(str(min_amount)) if min_amount is not None else None,
        max_amount=Decimal(str(max_amount)) if max_amount is not None else None,
        page=page,
        page_size=page_size,
    )
    return ExpensePage(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )


@router.get("/summary", response_model=ExpenseSummaryRead)
def summarize_expenses(
    group_by: ExpenseSummaryGroupBy = Query(),
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    # Multi-seleccion: coincide si el gasto tiene cualquiera de los ids.
    category_ids: list[int] | None = Query(default=None),
    payment_method_ids: list[int] | None = Query(default=None),
    tag_ids: list[int] | None = Query(default=None),
    min_amount: float | None = Query(default=None, ge=0),
    max_amount: float | None = Query(default=None, ge=0),
    user_id: int = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpenseSummaryRead:
    """Mismos filtros que el listado, agregados por `group_by` (para graficos)."""
    return service.summarize_expenses(
        user_id=user_id,
        group_by=group_by,
        start_date=start_date,
        end_date=end_date,
        category_ids=category_ids,
        payment_method_ids=payment_method_ids,
        tag_ids=tag_ids,
        min_amount=Decimal(str(min_amount)) if min_amount is not None else None,
        max_amount=Decimal(str(max_amount)) if max_amount is not None else None,
    )


@router.put("/{expense_id}", response_model=ExpenseRead)
def update_expense(
    expense_id: int,
    payload: ExpenseUpdate,
    user_id: int = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpenseRead:
    try:
        return service.update_expense(
            expense_id,
            user_id=user_id,
            name=payload.name,
            amount=Decimal(str(payload.amount)),
            recorded_on=payload.recorded_on,
            note=payload.note,
            payment_method_id=payload.payment_method_id,
            category_id=payload.category_id,
            tag_ids=payload.tag_ids,
        )
    except ExpenseNotFoundError:
        raise HTTPException(status_code=404, detail="Registro de gasto no encontrado")
    except (ExpenseCategoryNotFoundError, PaymentMethodNotFoundError, TagNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.delete("/{expense_id}", status_code=204)
def delete_expense(
    expense_id: int,
    user_id: int = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> None:
    try:
        service.delete_expense(expense_id, user_id=user_id)
    except ExpenseNotFoundError:
        raise HTTPException(status_code=404, detail="Registro de gasto no encontrado")
