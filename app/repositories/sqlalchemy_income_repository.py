"""Implementacion de los repositories de ingresos sobre SQLAlchemy/Postgres.

Una clase generica para el CRUD comun a ambas tablas; la de intereses suma
las consultas que solo tienen sentido por periodo.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.db.models.finance import DirectIncome, InterestIncome, Tag
from app.repositories.income_repository import IncomeFilters


class SqlAlchemyIncomeRepository[IncomeRecord: (DirectIncome, InterestIncome)]:
    def __init__(self, db: Session, model: type[IncomeRecord]) -> None:
        self._db = db
        self._model = model

    def _conditions(self, user_id: int, filters: IncomeFilters) -> list[ColumnElement[bool]]:
        model = self._model
        conditions = [model.user_id == user_id]
        if filters.start_date is not None:
            conditions.append(model.recorded_on >= filters.start_date)
        if filters.end_date is not None:
            conditions.append(model.recorded_on <= filters.end_date)
        if filters.source_id is not None:
            conditions.append(model.source_id == filters.source_id)
        if filters.subcategory_id is not None:
            conditions.append(model.subcategory_id == filters.subcategory_id)
        if filters.tag_ids:
            conditions.append(model.tags.any(Tag.id.in_(filters.tag_ids)))
        if filters.min_amount is not None:
            conditions.append(model.amount >= filters.min_amount)
        if filters.max_amount is not None:
            conditions.append(model.amount <= filters.max_amount)
        return conditions

    def create(
        self, *, user_id: int, fields: Mapping[str, Any], tags: Sequence[Tag]
    ) -> IncomeRecord:
        record = self._model(user_id=user_id, tags=list(tags), **fields)
        self._db.add(record)
        self._db.flush()
        return record

    def list(
        self, *, user_id: int, filters: IncomeFilters, offset: int, limit: int
    ) -> tuple[Sequence[IncomeRecord], int]:
        conditions = self._conditions(user_id, filters)
        total = self._db.scalar(select(func.count()).select_from(self._model).where(*conditions))
        items = (
            self._db.execute(
                select(self._model)
                .where(*conditions)
                .order_by(self._model.recorded_on.desc(), self._model.id.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total or 0

    def update(
        self, record_id: int, *, user_id: int, fields: Mapping[str, Any], tags: Sequence[Tag]
    ) -> IncomeRecord | None:
        record = self._db.get(self._model, record_id)
        if record is None or record.user_id != user_id:
            return None

        for name, value in fields.items():
            setattr(record, name, value)
        record.tags = list(tags)
        record.updated_at = datetime.now(UTC)
        self._db.flush()
        # Mismo motivo que en SqlAlchemyExpenseRepository.update: cambiar el
        # *_id no refresca la relationship ya cargada por el get().
        self._db.expire(record, ["source", "subcategory"])
        return record

    def delete(self, record_id: int, *, user_id: int) -> bool:
        record = self._db.get(self._model, record_id)
        if record is None or record.user_id != user_id:
            return False
        self._db.delete(record)
        self._db.flush()
        return True


class SqlAlchemyInterestIncomeRepository(SqlAlchemyIncomeRepository[InterestIncome]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, InterestIncome)

    def find_period(self, *, user_id: int, source_id: int, period_start: date) -> int | None:
        return self._db.scalar(
            select(InterestIncome.id).where(
                InterestIncome.user_id == user_id,
                InterestIncome.source_id == source_id,
                InterestIncome.recorded_on == period_start,
            )
        )

    def list_end_balances(self, *, user_id: int) -> Sequence[tuple[int, date, Decimal]]:
        rows = self._db.execute(
            select(
                InterestIncome.source_id,
                InterestIncome.recorded_on,
                InterestIncome.end_of_month_amount,
            )
            .where(
                InterestIncome.user_id == user_id,
                InterestIncome.end_of_month_amount.is_not(None),
            )
            .order_by(InterestIncome.recorded_on)
        )
        return [(source_id, recorded_on, amount) for source_id, recorded_on, amount in rows]
