"""Logica de negocio de registros de gasto. Las rutas dependen de esto,
nunca del repository directamente."""

import math
from datetime import date
from decimal import Decimal

from app.db.models.finance import Tag
from app.repositories.expense_repository import ExpenseRepository
from app.repositories.finance_catalog_repository import FinanceCatalogRepository
from app.schemas.finance import (
    ExpenseRead,
    ExpenseSummaryBucket,
    ExpenseSummaryGroupBy,
    ExpenseSummaryRead,
)
from app.services.errors import (
    ExpenseCategoryNotFoundError,
    ExpenseNotFoundError,
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

    def _validate_references(
        self, *, user_id: int, category_id: int, payment_method_id: int, tag_ids: list[int]
    ) -> list[Tag]:
        """Comun a create/update: valida que categoria, metodo de pago y tags
        existan (los tags, ademas, del usuario) antes de tocar el repository."""
        if self._catalog_repository.get_category(category_id) is None:
            raise ExpenseCategoryNotFoundError(category_id)
        if self._catalog_repository.get_payment_method(payment_method_id) is None:
            raise PaymentMethodNotFoundError(payment_method_id)

        tags = self._catalog_repository.list_tags_by_ids(user_id, tag_ids)
        missing_tag_ids = set(tag_ids) - {tag.id for tag in tags}
        if missing_tag_ids:
            raise TagNotFoundError(missing_tag_ids)
        return list(tags)

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
        tags = self._validate_references(
            user_id=user_id,
            category_id=category_id,
            payment_method_id=payment_method_id,
            tag_ids=tag_ids,
        )

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

    def update_expense(
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
        tag_ids: list[int],
    ) -> ExpenseRead:
        tags = self._validate_references(
            user_id=user_id,
            category_id=category_id,
            payment_method_id=payment_method_id,
            tag_ids=tag_ids,
        )

        record = self._expense_repository.update(
            expense_id,
            user_id=user_id,
            name=name,
            amount=amount,
            recorded_on=recorded_on,
            note=note,
            payment_method_id=payment_method_id,
            category_id=category_id,
            tags=tags,
        )
        if record is None:
            raise ExpenseNotFoundError(expense_id)
        return expense_to_read(record)

    def delete_expense(self, expense_id: int, *, user_id: int) -> None:
        deleted = self._expense_repository.delete(expense_id, user_id=user_id)
        if not deleted:
            raise ExpenseNotFoundError(expense_id)

    def list_expenses(
        self,
        *,
        user_id: int,
        start_date: date | None,
        end_date: date | None,
        category_ids: list[int] | None = None,
        payment_method_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
        page: int,
        page_size: int,
    ) -> tuple[list[ExpenseRead], int, int]:
        offset = (page - 1) * page_size
        items, total = self._expense_repository.list(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            category_ids=category_ids,
            payment_method_ids=payment_method_ids,
            tag_ids=tag_ids,
            min_amount=min_amount,
            max_amount=max_amount,
            offset=offset,
            limit=page_size,
        )
        total_pages = math.ceil(total / page_size) if total else 0
        return [expense_to_read(item) for item in items], total, total_pages

    def summarize_expenses(
        self,
        *,
        user_id: int,
        group_by: ExpenseSummaryGroupBy,
        start_date: date | None,
        end_date: date | None,
        category_ids: list[int] | None = None,
        payment_method_ids: list[int] | None = None,
        tag_ids: list[int] | None = None,
        min_amount: Decimal | None = None,
        max_amount: Decimal | None = None,
    ) -> ExpenseSummaryRead:
        rows, total, count = self._expense_repository.summarize(
            user_id=user_id,
            group_by=group_by.value,
            start_date=start_date,
            end_date=end_date,
            category_ids=category_ids,
            payment_method_ids=payment_method_ids,
            tag_ids=tag_ids,
            min_amount=min_amount,
            max_amount=max_amount,
        )
        return ExpenseSummaryRead(
            group_by=group_by,
            total=float(total),
            count=count,
            buckets=[
                ExpenseSummaryBucket(
                    key=row.key,
                    label=row.label,
                    icon_key=row.icon_key,
                    color_key=row.color_key,
                    total=float(row.total),
                    count=row.count,
                )
                for row in rows
            ],
        )
