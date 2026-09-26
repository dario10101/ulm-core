"""Esquemas Pydantic de entrada/salida del modulo de finanzas."""

from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class CatalogStatus(str, Enum):
    ENABLED = "ENABLED"
    DISABLED = "DISABLED"


class CategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    icon_key: str
    color_key: str
    status: CatalogStatus


class PaymentMethodRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    icon_key: str
    color_key: str
    status: CatalogStatus


class TagRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    color_key: str
    status: CatalogStatus


class ExpenseOptionsRead(BaseModel):
    """Los 3 catalogos (ya filtrados a status=ENABLED) en un solo viaje, para
    que "Add record" no tenga que hacer 3 requests separados."""

    categories: list[CategoryRead]
    payment_methods: list[PaymentMethodRead]
    tags: list[TagRead]


class ExpenseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, description="Monto en COP")
    recorded_on: date
    note: str | None = Field(default=None, max_length=2000)
    payment_method_id: int
    category_id: int
    tag_ids: list[int] = Field(default_factory=list)


class ExpenseRead(BaseModel):
    id: int
    user_id: int
    name: str
    amount: float
    recorded_on: date
    note: str | None
    category: CategoryRead
    payment_method: PaymentMethodRead
    tags: list[TagRead]
    created_at: datetime
    updated_at: datetime | None


class ExpensePage(BaseModel):
    items: list[ExpenseRead]
    total: int
    page: int
    page_size: int
    total_pages: int
