"""Parametros del dominio de finanzas que cada usuario administra sobre sus
datos: tags, fuentes y subcategorias de ingreso ("View records" -> Manage).
Exige el permiso `finances` (ver PRIVATE_ROUTERS en app/main.py).

DELETE responde 200 con el resultado y no 204: el cliente necesita saber si
el item se borro o se archivo (borrado hibrido)."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id, get_finance_params_service
from app.api.errors import http_error
from app.schemas.finance import (
    CatalogDeleteRead,
    IncomeSourceAdminRead,
    IncomeSourceWrite,
    IncomeSubcategoryAdminRead,
    IncomeSubcategoryWrite,
    TagAdminRead,
    TagWrite,
)
from app.services.errors import DomainError
from app.services.finance_params_service import FinanceParamsService

router = APIRouter(prefix="/finances", tags=["finance params"])


# --- Tags ---


@router.get("/tags", response_model=list[TagAdminRead])
def list_tags(
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> list[TagAdminRead]:
    return service.list_tags(user_id=user_id)


@router.post("/tags", response_model=TagAdminRead, status_code=201)
def create_tag(
    payload: TagWrite,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> TagAdminRead:
    try:
        return service.create_tag(user_id=user_id, payload=payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/tags/{tag_id}", response_model=TagAdminRead)
def update_tag(
    tag_id: int,
    payload: TagWrite,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> TagAdminRead:
    try:
        return service.update_tag(tag_id, user_id=user_id, payload=payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/tags/{tag_id}", response_model=CatalogDeleteRead)
def delete_tag(
    tag_id: int,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_tag(tag_id, user_id=user_id))
    except DomainError as exc:
        raise http_error(exc)


# --- Fuentes de ingreso ---


@router.get("/income-sources", response_model=list[IncomeSourceAdminRead])
def list_income_sources(
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> list[IncomeSourceAdminRead]:
    return service.list_sources(user_id=user_id)


@router.post("/income-sources", response_model=IncomeSourceAdminRead, status_code=201)
def create_income_source(
    payload: IncomeSourceWrite,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> IncomeSourceAdminRead:
    try:
        return service.create_source(user_id=user_id, payload=payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/income-sources/{source_id}", response_model=IncomeSourceAdminRead)
def update_income_source(
    source_id: int,
    payload: IncomeSourceWrite,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> IncomeSourceAdminRead:
    try:
        return service.update_source(source_id, user_id=user_id, payload=payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/income-sources/{source_id}", response_model=CatalogDeleteRead)
def delete_income_source(
    source_id: int,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_source(source_id, user_id=user_id))
    except DomainError as exc:
        raise http_error(exc)


# --- Subcategorias de ingreso ---


@router.get("/income-subcategories", response_model=list[IncomeSubcategoryAdminRead])
def list_income_subcategories(
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> list[IncomeSubcategoryAdminRead]:
    return service.list_subcategories(user_id=user_id)


@router.post("/income-subcategories", response_model=IncomeSubcategoryAdminRead, status_code=201)
def create_income_subcategory(
    payload: IncomeSubcategoryWrite,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> IncomeSubcategoryAdminRead:
    try:
        return service.create_subcategory(user_id=user_id, payload=payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/income-subcategories/{subcategory_id}", response_model=IncomeSubcategoryAdminRead)
def update_income_subcategory(
    subcategory_id: int,
    payload: IncomeSubcategoryWrite,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> IncomeSubcategoryAdminRead:
    try:
        return service.update_subcategory(subcategory_id, user_id=user_id, payload=payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/income-subcategories/{subcategory_id}", response_model=CatalogDeleteRead)
def delete_income_subcategory(
    subcategory_id: int,
    user_id: int = Depends(get_current_user_id),
    service: FinanceParamsService = Depends(get_finance_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_subcategory(subcategory_id, user_id=user_id))
    except DomainError as exc:
        raise http_error(exc)
