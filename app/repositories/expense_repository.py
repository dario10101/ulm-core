"""Interfaz (Protocol) del acceso a datos de registros de gasto.

La capa de servicio depende solo de esto, nunca de una implementacion
concreta (ver app/repositories/weight_repository.py para el mismo patron).
"""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal
from typing import Protocol

from app.db.models.finance import Expense, Tag


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
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Expense], int]: ...
