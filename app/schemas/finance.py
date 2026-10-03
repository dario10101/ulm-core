"""Esquemas Pydantic de entrada/salida del modulo de finanzas."""

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

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


class ExpenseUpdate(ExpenseCreate):
    """Mismos campos que la creacion: es un reemplazo completo del registro."""


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


class ExpenseSummaryGroupBy(str, Enum):
    CATEGORY = "category"
    TAG = "tag"
    PAYMENT_METHOD = "payment_method"
    MONTH = "month"
    YEAR = "year"


class ExpenseSummaryBucket(BaseModel):
    key: str
    label: str
    icon_key: str | None
    color_key: str | None
    total: float
    count: int


class ExpenseSummaryRead(BaseModel):
    """Agregado para "Finance analysis". `total`/`count` son del conjunto
    filtrado completo; con group_by=tag la suma de los buckets puede superarlo
    (un gasto con varios tags aparece en cada uno)."""

    group_by: ExpenseSummaryGroupBy
    total: float
    count: int
    buckets: list[ExpenseSummaryBucket]


# --- Ingresos ---


class IncomeKind(str, Enum):
    """A que tipo de ingreso aplica una fuente/subcategoria. ALL = ambos."""

    DIRECT = "DIRECT"
    INTEREST = "INTEREST"
    ALL = "ALL"


# Montos de ingreso: Decimal con 2 decimales validado en la entrada (un float
# no puede rechazar 0.001); en la salida se devuelve float, igual que gastos,
# porque Pydantic serializa Decimal como string en JSON.
Amount = Annotated[Decimal, Field(max_digits=14, decimal_places=2)]


class IncomeSourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    type: IncomeKind


class IncomeSubcategoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    source_id: int
    name: str
    type: IncomeKind


class InterestEndBalance(BaseModel):
    """Saldo final de un mes ya registrado, para ofrecer "usar saldo del mes
    anterior" sin otro request al cambiar de periodo en el formulario."""

    source_id: int
    period: str  # "YYYY-MM"
    end_of_month_amount: float


class IncomeOptionsRead(BaseModel):
    """Todo lo que necesita "Add record -> Income" (directo e intereses) en un
    solo viaje."""

    sources: list[IncomeSourceRead]
    subcategories: list[IncomeSubcategoryRead]
    tags: list[TagRead]
    interest_end_balances: list[InterestEndBalance]


class DirectIncomeCreate(BaseModel):
    amount: Amount = Field(gt=0, description="Monto en COP")
    recorded_on: date
    note: str | None = Field(default=None, max_length=2000)
    source_id: int
    subcategory_id: int
    tag_ids: list[int] = Field(default_factory=list)


class DirectIncomeUpdate(DirectIncomeCreate):
    """Reemplazo completo del registro."""


class DirectIncomeRead(BaseModel):
    id: int
    user_id: int
    amount: float
    recorded_on: date
    note: str | None
    source: IncomeSourceRead
    subcategory: IncomeSubcategoryRead
    tags: list[TagRead]
    created_at: datetime
    updated_at: datetime | None


class DirectIncomePage(BaseModel):
    items: list[DirectIncomeRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class InterestIncomeCreate(BaseModel):
    """`recorded_on` puede ser cualquier dia: el service lo lleva al dia 1 del
    mes. El modo manual/automatico del formulario no existe aca: el backend
    guarda el interes que llega, sin recalcularlo."""

    amount: Amount = Field(description="Interes del mes en COP; puede ser negativo")
    recorded_on: date
    start_of_month_amount: Amount | None = Field(default=None, ge=0)
    end_of_month_amount: Amount | None = Field(default=None, ge=0)
    deposits_amount: Amount = Field(default=Decimal(0), ge=0)
    withdrawals_amount: Amount = Field(default=Decimal(0), ge=0)
    note: str | None = Field(default=None, max_length=2000)
    source_id: int
    subcategory_id: int
    tag_ids: list[int] = Field(default_factory=list)


class InterestIncomeUpdate(InterestIncomeCreate):
    """Reemplazo completo del registro."""


class InterestIncomeRead(BaseModel):
    id: int
    user_id: int
    amount: float
    recorded_on: date
    start_of_month_amount: float | None
    end_of_month_amount: float | None
    deposits_amount: float
    withdrawals_amount: float
    note: str | None
    source: IncomeSourceRead
    subcategory: IncomeSubcategoryRead
    tags: list[TagRead]
    created_at: datetime
    updated_at: datetime | None


class InterestIncomePage(BaseModel):
    items: list[InterestIncomeRead]
    total: int
    page: int
    page_size: int
    total_pages: int


# --- Analisis de ingresos ---


class IncomeSummaryGroupBy(str, Enum):
    SOURCE = "source"
    SUBCATEGORY = "subcategory"
    TAG = "tag"
    MONTH = "month"
    YEAR = "year"


class IncomeStackBy(str, Enum):
    """Desglose de cada periodo en las vistas por mes/año (columnas apiladas)."""

    SOURCE = "source"
    SUBCATEGORY = "subcategory"


class IncomeKindFilter(str, Enum):
    DIRECT = "direct"
    INTEREST = "interest"


class IncomeSummarySegment(BaseModel):
    key: str
    label: str
    total: float


class IncomeSummaryBucket(BaseModel):
    """`key` es el id (fuente/subcategoria/tag, "none" = sin tag) o el
    periodo ("2026-09" / "2026"). `parent_label` es la fuente de una
    subcategoria (hay nombres repetidos entre fuentes)."""

    key: str
    label: str
    parent_label: str | None = None
    color_key: str | None = None
    total: float
    count: int
    segments: list[IncomeSummarySegment] = Field(default_factory=list)


class IncomeSummaryRead(BaseModel):
    """Agregado para "Finance analysis -> Income", sumando directos e
    intereses. Con group_by=tag la suma de buckets puede superar `total`
    (un ingreso con varios tags aparece en cada uno)."""

    group_by: IncomeSummaryGroupBy
    stack_by: IncomeStackBy | None
    total: float
    count: int
    direct_total: float
    interest_total: float
    buckets: list[IncomeSummaryBucket]
