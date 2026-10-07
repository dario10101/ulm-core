"""Interfaz (Protocol) del acceso a datos de registros de gasto.

La capa de servicio depende solo de esto, nunca de una implementacion
concreta (ver app/repositories/weight_repository.py para el mismo patron).
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Literal, NamedTuple, Protocol

from app.db.models.finance import Expense, Tag

ExpenseGroupBy = Literal["category", "tag", "payment_method", "month", "year"]


class ExpenseSummarySegmentRow(NamedTuple):
    """Total de una categoria dentro de un periodo (columnas apiladas)."""

    key: str
    label: str
    icon_key: str | None
    color_key: str | None
    total: Decimal


class ExpenseSummaryRow(NamedTuple):
    """Un grupo agregado. `key` es el id (categoria/metodo/tag, "none" para
    gastos sin tag) o el periodo ("2026-09" / "2026"). Solo los periodos
    (month/year) traen `segments`: su desglose por categoria."""

    key: str
    label: str
    icon_key: str | None
    color_key: str | None
    total: Decimal
    count: int
    segments: tuple[ExpenseSummarySegmentRow, ...] = ()


class ExpenseRepository(Protocol):
    def create(
        self,
        *,
        user_id: int,
        name: str,
        amount: Decimal,
        recorded_on: date,
        note: str | None,
        payment_method_id: int,
        category_id: int,
        tags: Sequence[Tag],
    ) -> Expense: ...

    def list(
        self,
        *,
        user_id: int,
        start_date: date | None,
        end_date: date | None,
        category_ids: Sequence[int] | None,
        payment_method_ids: Sequence[int] | None,
        tag_ids: Sequence[int] | None,
        min_amount: Decimal | None,
        max_amount: Decimal | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Expense], int]: ...

    def summarize(
        self,
        *,
        user_id: int,
        group_by: ExpenseGroupBy,
        start_date: date | None,
        end_date: date | None,
        category_ids: Sequence[int] | None,
        payment_method_ids: Sequence[int] | None,
        tag_ids: Sequence[int] | None,
        min_amount: Decimal | None,
        max_amount: Decimal | None,
    ) -> tuple[Sequence[ExpenseSummaryRow], Decimal, int]:
        """Grupos + total y cantidad globales del filtro. El total global se
        calcula aparte: agrupando por tag un gasto con 2 tags cuenta 2 veces,
        asi que sumar los grupos no daria el gasto real."""
        ...

    def update(
        self,
        expense_id: int,
        *,
        user_id: int,
        name: str,
        amount: Decimal,
        recorded_on: date,
        note: str | None,
        payment_method_id: int,
        category_id: int,
        tags: Sequence[Tag],
    ) -> Expense | None:
        """Devuelve None si el registro no existe **o no es de ese usuario**:
        quien no es dueño no puede distinguir un caso del otro."""
        ...

    def delete(self, expense_id: int, *, user_id: int) -> bool:
        """False si no existe o no es de ese usuario (misma razon que update)."""
        ...
