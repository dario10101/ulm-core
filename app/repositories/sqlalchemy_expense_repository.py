"""Implementacion del ExpenseRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.finance import Expense, Tag


class SqlAlchemyExpenseRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

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
    ) -> Expense:
        record = Expense(
            user_id=user_id,
            name=name,
            amount=amount,
            recorded_on=recorded_on,
            note=note,
            payment_method_id=payment_method_id,
            category_id=category_id,
            tags=list(tags),
        )
        self._db.add(record)
        self._db.flush()
        return record

    def list(
        self,
        *,
        user_id: int,
        start_date: date | None,
        end_date: date | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Expense], int]:
        conditions = [Expense.user_id == user_id]
        if start_date is not None:
            conditions.append(Expense.recorded_on >= start_date)
        if end_date is not None:
            conditions.append(Expense.recorded_on <= end_date)

        total = self._db.scalar(select(func.count()).select_from(Expense).where(*conditions))

        items = (
            self._db.execute(
                select(Expense)
                .where(*conditions)
                .order_by(Expense.recorded_on.desc(), Expense.id.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total or 0
