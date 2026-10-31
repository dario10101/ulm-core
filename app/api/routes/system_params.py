"""Parametros globales del sistema (Settings -> System): plantillas para
usuarios nuevos (categorias de gasto, metodos de pago, fuentes y
subcategorias de ingreso), festivos/fechas especiales y datos de acceso.
Solo el admin (ver PRIVATE_ROUTERS en app/main.py)."""

from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_calendar_admin_service, get_system_params_service
from app.api.errors import http_error
from app.core.config import settings
from app.schemas.calendar_event import (
    CalendarYearRead,
    CldEventRead,
    CldEventWrite,
    ImportHolidaysRequest,
)
from app.schemas.finance import (
    CatalogDeleteRead,
    DefaultIconCatalogRead,
    DefaultIconCatalogWrite,
    DefaultIncomeSourceRead,
    DefaultIncomeSourceWrite,
    DefaultIncomeSubcategoryRead,
    DefaultIncomeSubcategoryWrite,
)
from app.schemas.user import AccessInfoRead
from app.services.calendar_admin_service import CalendarAdminService
from app.services.errors import DomainError
from app.services.system_params_service import SystemParamsService

router = APIRouter(prefix="/system", tags=["system params"])

GOOGLE_AUDIENCE_URL = "https://console.cloud.google.com/auth/audience"


@router.get("/access", response_model=AccessInfoRead)
def get_access_info() -> AccessInfoRead:
    url = GOOGLE_AUDIENCE_URL
    if settings.google_cloud_project:
        url = f"{url}?{urlencode({'project': settings.google_cloud_project})}"
    return AccessInfoRead(registration_mode=settings.registration_mode, google_audience_url=url)


# --- Plantillas para usuarios nuevos ---
#
# DELETE siempre responde DELETED (nada referencia una plantilla); conserva la
# forma de los demas catalogos para que el cliente los trate igual.
#
# --- Plantilla de categorias de gasto ---


@router.get("/expense-categories", response_model=list[DefaultIconCatalogRead])
def list_default_expense_categories(
    service: SystemParamsService = Depends(get_system_params_service),
) -> list[DefaultIconCatalogRead]:
    return service.list_default_categories()


@router.post("/expense-categories", response_model=DefaultIconCatalogRead, status_code=201)
def create_default_expense_category(
    payload: DefaultIconCatalogWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> DefaultIconCatalogRead:
    try:
        return service.create_default_category(payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/expense-categories/{category_id}", response_model=DefaultIconCatalogRead)
def update_default_expense_category(
    category_id: int,
    payload: DefaultIconCatalogWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> DefaultIconCatalogRead:
    try:
        return service.update_default_category(category_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/expense-categories/{category_id}", response_model=CatalogDeleteRead)
def delete_default_expense_category(
    category_id: int,
    service: SystemParamsService = Depends(get_system_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_default_category(category_id))
    except DomainError as exc:
        raise http_error(exc)


# --- Plantilla de metodos de pago ---


@router.get("/payment-methods", response_model=list[DefaultIconCatalogRead])
def list_default_payment_methods(
    service: SystemParamsService = Depends(get_system_params_service),
) -> list[DefaultIconCatalogRead]:
    return service.list_default_payment_methods()


@router.post("/payment-methods", response_model=DefaultIconCatalogRead, status_code=201)
def create_default_payment_method(
    payload: DefaultIconCatalogWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> DefaultIconCatalogRead:
    try:
        return service.create_default_payment_method(payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/payment-methods/{payment_method_id}", response_model=DefaultIconCatalogRead)
def update_default_payment_method(
    payment_method_id: int,
    payload: DefaultIconCatalogWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> DefaultIconCatalogRead:
    try:
        return service.update_default_payment_method(payment_method_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/payment-methods/{payment_method_id}", response_model=CatalogDeleteRead)
def delete_default_payment_method(
    payment_method_id: int,
    service: SystemParamsService = Depends(get_system_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_default_payment_method(payment_method_id))
    except DomainError as exc:
        raise http_error(exc)


# --- Plantilla de fuentes de ingreso (borrar una borra sus subcategorias) ---


@router.get("/income-sources", response_model=list[DefaultIncomeSourceRead])
def list_default_income_sources(
    service: SystemParamsService = Depends(get_system_params_service),
) -> list[DefaultIncomeSourceRead]:
    return service.list_default_sources()


@router.post("/income-sources", response_model=DefaultIncomeSourceRead, status_code=201)
def create_default_income_source(
    payload: DefaultIncomeSourceWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> DefaultIncomeSourceRead:
    try:
        return service.create_default_source(payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/income-sources/{source_id}", response_model=DefaultIncomeSourceRead)
def update_default_income_source(
    source_id: int,
    payload: DefaultIncomeSourceWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> DefaultIncomeSourceRead:
    try:
        return service.update_default_source(source_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/income-sources/{source_id}", response_model=CatalogDeleteRead)
def delete_default_income_source(
    source_id: int,
    service: SystemParamsService = Depends(get_system_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_default_source(source_id))
    except DomainError as exc:
        raise http_error(exc)


# --- Plantilla de subcategorias de ingreso ---


@router.get("/income-subcategories", response_model=list[DefaultIncomeSubcategoryRead])
def list_default_income_subcategories(
    service: SystemParamsService = Depends(get_system_params_service),
) -> list[DefaultIncomeSubcategoryRead]:
    return service.list_default_subcategories()


@router.post("/income-subcategories", response_model=DefaultIncomeSubcategoryRead, status_code=201)
def create_default_income_subcategory(
    payload: DefaultIncomeSubcategoryWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> DefaultIncomeSubcategoryRead:
    try:
        return service.create_default_subcategory(payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/income-subcategories/{subcategory_id}", response_model=DefaultIncomeSubcategoryRead)
def update_default_income_subcategory(
    subcategory_id: int,
    payload: DefaultIncomeSubcategoryWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> DefaultIncomeSubcategoryRead:
    try:
        return service.update_default_subcategory(subcategory_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/income-subcategories/{subcategory_id}", response_model=CatalogDeleteRead)
def delete_default_income_subcategory(
    subcategory_id: int,
    service: SystemParamsService = Depends(get_system_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_default_subcategory(subcategory_id))
    except DomainError as exc:
        raise http_error(exc)


# --- Festivos y fechas especiales (cld_events) ---


@router.get("/calendar-events", response_model=CalendarYearRead)
def get_calendar_year(
    year: int = Query(ge=1900, le=2200),
    service: CalendarAdminService = Depends(get_calendar_admin_service),
) -> CalendarYearRead:
    return service.get_year(year)


@router.post("/calendar-events/import-holidays", response_model=CalendarYearRead)
def import_missing_holidays(
    payload: ImportHolidaysRequest,
    service: CalendarAdminService = Depends(get_calendar_admin_service),
) -> CalendarYearRead:
    return service.import_missing_holidays(payload.year)


@router.post("/calendar-events", response_model=CldEventRead, status_code=201)
def create_calendar_event(
    payload: CldEventWrite,
    service: CalendarAdminService = Depends(get_calendar_admin_service),
) -> CldEventRead:
    return service.create(payload)


@router.put("/calendar-events/{event_id}", response_model=CldEventRead)
def update_calendar_event(
    event_id: int,
    payload: CldEventWrite,
    service: CalendarAdminService = Depends(get_calendar_admin_service),
) -> CldEventRead:
    try:
        return service.update(event_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/calendar-events/{event_id}", status_code=204)
def delete_calendar_event(
    event_id: int,
    service: CalendarAdminService = Depends(get_calendar_admin_service),
) -> None:
    try:
        service.delete(event_id)
    except DomainError as exc:
        raise http_error(exc)
