"""Rutas de registros de gasto y de sus catalogos (categorias, metodos de
pago, tags). Solo hablan con ExpenseService/FinanceCatalogService (nunca con
el repository ni con la sesion de base de datos directamente)."""

from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user_id, get_expense_service, get_finance_catalog_service
from app.schemas.finance import ExpenseCreate, ExpenseOptionsRead, ExpensePage, ExpenseRead
from app.services.errors import (
    ExpenseCategoryNotFoundError,
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
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    user_id: int = Depends(get_current_user_id),
    service: ExpenseService = Depends(get_expense_service),
) -> ExpensePage:
    items, total, total_pages = service.list_expenses(
        user_id=user_id,
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
    return ExpensePage(
        items=items, total=total, page=page, page_size=page_size, total_pages=total_pages
    )
