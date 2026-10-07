"""Implementacion del ExpenseRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import ColumnElement, extract, func, select
from sqlalchemy.orm import Session

from app.db.models.finance import Category, Expense, ExpenseTag, PaymentMethod, Tag
from app.repositories.expense_repository import (
    ExpenseGroupBy,
    ExpenseSummaryRow,
    ExpenseSummarySegmentRow,
)


def _filter_conditions(
    *,
    user_id: int,
    start_date: date | None,
    end_date: date | None,
    category_ids: Sequence[int] | None,
    payment_method_ids: Sequence[int] | None,
    tag_ids: Sequence[int] | None,
    min_amount: Decimal | None,
    max_amount: Decimal | None,
) -> list[ColumnElement[bool]]:
    """Filtros comunes al listado y al resumen: ambos deben ver exactamente
    el mismo conjunto de gastos para que los numeros cuadren."""
    conditions = [Expense.user_id == user_id]
    if start_date is not None:
        conditions.append(Expense.recorded_on >= start_date)
    if end_date is not None:
        conditions.append(Expense.recorded_on <= end_date)
    if category_ids:
        conditions.append(Expense.category_id.in_(category_ids))
    if payment_method_ids:
        conditions.append(Expense.payment_method_id.in_(payment_method_ids))
    if tag_ids:
        conditions.append(Expense.tags.any(Tag.id.in_(tag_ids)))
    if min_amount is not None:
        conditions.append(Expense.amount >= min_amount)
    if max_amount is not None:
        conditions.append(Expense.amount <= max_amount)
    return conditions


def _period_key(parts: Sequence[object]) -> str:
    """("2026", "9") -> "2026-09"; ("2026",) -> "2026"."""
    return "-".join(
        f"{int(part):04d}" if i == 0 else f"{int(part):02d}" for i, part in enumerate(parts)
    )


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
        category_ids: Sequence[int] | None,
        payment_method_ids: Sequence[int] | None,
        tag_ids: Sequence[int] | None,
        min_amount: Decimal | None,
        max_amount: Decimal | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Expense], int]:
        conditions = _filter_conditions(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            category_ids=category_ids,
            payment_method_ids=payment_method_ids,
            tag_ids=tag_ids,
            min_amount=min_amount,
            max_amount=max_amount,
        )

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
        conditions = _filter_conditions(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            category_ids=category_ids,
            payment_method_ids=payment_method_ids,
            tag_ids=tag_ids,
            min_amount=min_amount,
            max_amount=max_amount,
        )
        total_amount = func.sum(Expense.amount)

        if group_by in ("category", "payment_method"):
            catalog = Category if group_by == "category" else PaymentMethod
            fk = Expense.category_id if group_by == "category" else Expense.payment_method_id
            result = self._db.execute(
                select(
                    catalog.id,
                    catalog.name,
                    catalog.icon_key,
                    catalog.color_key,
                    total_amount,
                    func.count(Expense.id),
                )
                .join(catalog, fk == catalog.id)
                .where(*conditions)
                .group_by(catalog.id, catalog.name, catalog.icon_key, catalog.color_key)
                .order_by(total_amount.desc())
            )
            rows = [
                ExpenseSummaryRow(str(id_), name, icon, color, total, count)
                for id_, name, icon, color, total, count in result
            ]
        elif group_by == "tag":
            # LEFT JOIN: los gastos sin tag quedan en un grupo propio (tag NULL)
            # en vez de desaparecer del analisis.
            result = self._db.execute(
                select(Tag.id, Tag.name, Tag.color_key, total_amount, func.count(Expense.id))
                .select_from(Expense)
                .outerjoin(ExpenseTag, ExpenseTag.expense_id == Expense.id)
                .outerjoin(Tag, Tag.id == ExpenseTag.tag_id)
                .where(*conditions)
                .group_by(Tag.id, Tag.name, Tag.color_key)
                .order_by(total_amount.desc())
            )
            rows = [
                ExpenseSummaryRow(
                    str(id_) if id_ is not None else "none",
                    name if name is not None else "Untagged",
                    None,
                    color,
                    total,
                    count,
                )
                for id_, name, color, total, count in result
            ]
        else:
            # extract() en vez de date_trunc: funciona igual en Postgres y en
            # el SQLite de los tests (SQLAlchemy lo traduce a strftime ahi).
            year = extract("year", Expense.recorded_on)
            period = [year] if group_by == "year" else [year, extract("month", Expense.recorded_on)]
            result = self._db.execute(
                select(*period, total_amount, func.count(Expense.id))
                .where(*conditions)
                .group_by(*period)
                .order_by(*period)
            )
            # Desglose por categoria de cada periodo (para columnas apiladas):
            # una consulta aparte agrupada por periodo + categoria.
            segments: dict[str, list[ExpenseSummarySegmentRow]] = {}
            breakdown = self._db.execute(
                select(
                    *period,
                    Category.id,
                    Category.name,
                    Category.icon_key,
                    Category.color_key,
                    total_amount,
                )
                .join(Category, Expense.category_id == Category.id)
                .where(*conditions)
                .group_by(
                    *period, Category.id, Category.name, Category.icon_key, Category.color_key
                )
                .order_by(*period, total_amount.desc())
            )
            for row in breakdown:
                *parts, id_, name, icon, color, total = row
                segments.setdefault(_period_key(parts), []).append(
                    ExpenseSummarySegmentRow(str(id_), name, icon, color, total)
                )

            rows = []
            for row in result:
                *parts, total, count = row
                key = _period_key(parts)
                rows.append(
                    ExpenseSummaryRow(
                        key, key, None, None, total, count, tuple(segments.get(key, ()))
                    )
                )

        grand_total, grand_count = self._db.execute(
            select(func.coalesce(total_amount, 0), func.count(Expense.id)).where(*conditions)
        ).one()
        return rows, Decimal(grand_total), grand_count

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
        record = self._db.get(Expense, expense_id)
        if record is None or record.user_id != user_id:
            return None

        record.name = name
        record.amount = amount
        record.recorded_on = recorded_on
        record.note = note
        record.payment_method_id = payment_method_id
        record.category_id = category_id
        record.tags = list(tags)
        record.updated_at = datetime.now(UTC)
        self._db.flush()
        # category/payment_method son relationship (lazy="joined") cargadas
        # desde el get() de arriba: cambiar el *_id no las refresca solo, hay
        # que invalidarlas para que la proxima lectura traiga la fila nueva.
        self._db.expire(record, ["category", "payment_method"])
        return record

    def delete(self, expense_id: int, *, user_id: int) -> bool:
        record = self._db.get(Expense, expense_id)
        if record is None or record.user_id != user_id:
            return False

        self._db.delete(record)
        self._db.flush()
        return True
