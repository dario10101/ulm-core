"""Logica de negocio de registros de gasto. Las rutas dependen de esto,
nunca del repository directamente."""

import math
from datetime import date
from decimal import Decimal

from app.repositories.expense_repository import ExpenseRepository
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.schemas.finance import ExpenseRead
from app.services.errors import (
    ExpenseCategoryNotFoundError,
    PaymentMethodNotFoundError,
    TagNotFoundError,
)
from app.services.mappers import expense_to_read


class ExpenseService:
    def __init__(
        self,
        expense_repository: ExpenseRepository,
        catalog_repository: FinanceCatalogRepository,
    ) -> None:
        self._expense_repository = expense_repository
        self._catalog_repository = catalog_repository

    def create_expense(
        self,
        *,
        user_id: int,
        name: str,
        amount: Decimal,
        recorded_on: date,
        note: str | None,
        payment_method_id: int,
        category_id: int,
        tag_ids: list[int],
    ) -> ExpenseRead:
        if self._catalog_repository.get_category(category_id) is None:
            raise ExpenseCategoryNotFoundError(category_id)
        if self._catalog_repository.get_payment_method(payment_method_id) is None:
            raise PaymentMethodNotFoundError(payment_method_id)

        tags = self._catalog_repository.list_tags_by_ids(user_id, tag_ids)
        missing_tag_ids = set(tag_ids) - {tag.id for tag in tags}
        if missing_tag_ids:
            raise TagNotFoundError(missing_tag_ids)

        record = self._expense_repository.create(
            user_id=user_id,
            name=name,
            amount=amount,
            recorded_on=recorded_on,
            note=note,
            payment_method_id=payment_method_id,
            category_id=category_id,
            tags=tags,
        )
        return expense_to_read(record)

    def list_expenses(
        self,
        *,
        user_id: int,
        start_date: date | None,
        end_date: date | None,
        page: int,
        page_size: int,
    ) -> tuple[list[ExpenseRead], int, int]:
        offset = (page - 1) * page_size
        items, total = self._expense_repository.list(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            offset=offset,
            limit=page_size,
        )
        total_pages = math.ceil(total / page_size) if total else 0
        return [expense_to_read(item) for item in items], total, total_pages
