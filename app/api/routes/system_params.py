"""Parametros globales del sistema (Settings -> System): categorias de gasto,
metodos de pago, festivos/fechas especiales y datos de acceso. Solo el admin
(ver PRIVATE_ROUTERS en app/main.py)."""

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
    CategoryAdminRead,
    IconCatalogWrite,
    PaymentMethodAdminRead,
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


# --- Categorias de gasto ---


@router.get("/expense-categories", response_model=list[CategoryAdminRead])
def list_expense_categories(
    service: SystemParamsService = Depends(get_system_params_service),
) -> list[CategoryAdminRead]:
    return service.list_categories()


@router.post("/expense-categories", response_model=CategoryAdminRead, status_code=201)
def create_expense_category(
    payload: IconCatalogWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> CategoryAdminRead:
    try:
        return service.create_category(payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/expense-categories/{category_id}", response_model=CategoryAdminRead)
def update_expense_category(
    category_id: int,
    payload: IconCatalogWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> CategoryAdminRead:
    try:
        return service.update_category(category_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/expense-categories/{category_id}", response_model=CatalogDeleteRead)
def delete_expense_category(
    category_id: int,
    service: SystemParamsService = Depends(get_system_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_category(category_id))
    except DomainError as exc:
        raise http_error(exc)


# --- Metodos de pago ---


@router.get("/payment-methods", response_model=list[PaymentMethodAdminRead])
def list_payment_methods(
    service: SystemParamsService = Depends(get_system_params_service),
) -> list[PaymentMethodAdminRead]:
    return service.list_payment_methods()


@router.post("/payment-methods", response_model=PaymentMethodAdminRead, status_code=201)
def create_payment_method(
    payload: IconCatalogWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> PaymentMethodAdminRead:
    try:
        return service.create_payment_method(payload)
    except DomainError as exc:
        raise http_error(exc)


@router.put("/payment-methods/{payment_method_id}", response_model=PaymentMethodAdminRead)
def update_payment_method(
    payment_method_id: int,
    payload: IconCatalogWrite,
    service: SystemParamsService = Depends(get_system_params_service),
) -> PaymentMethodAdminRead:
    try:
        return service.update_payment_method(payment_method_id, payload)
    except DomainError as exc:
        raise http_error(exc)


@router.delete("/payment-methods/{payment_method_id}", response_model=CatalogDeleteRead)
def delete_payment_method(
    payment_method_id: int,
    service: SystemParamsService = Depends(get_system_params_service),
) -> CatalogDeleteRead:
    try:
        return CatalogDeleteRead(result=service.delete_payment_method(payment_method_id))
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
