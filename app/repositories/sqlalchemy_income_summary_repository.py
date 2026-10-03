"""Implementacion de IncomeSummaryRepository sobre SQLAlchemy/Postgres.

Directos e intereses viven en tablas distintas pero para el analisis son
"ingresos": se arma un UNION ALL con las columnas comunes (mas `kind`, para
poder distinguirlos) y todos los agregados se hacen sobre esa subconsulta.
"""

from collections.abc import Sequence
from decimal import Decimal

from sqlalchemy import String, and_, case, extract, func, literal, select, union_all
from sqlalchemy.orm import Session
from sqlalchemy.sql import Subquery

from app.db.models.finance import (
    DirectIncome,
    DirectIncomeTag,
    IncomeSource,
    IncomeSubcategory,
    InterestIncome,
    InterestIncomeTag,
    Tag,
)
from app.repositories.income_summary_repository import (
    IncomeGroupBy,
    IncomeStack,
    IncomeSummaryFilters,
    IncomeSummaryRow,
    IncomeTotals,
)

_TABLES = (
    ("direct", DirectIncome, DirectIncomeTag),
    ("interest", InterestIncome, InterestIncomeTag),
)


def _period_key(parts: Sequence[object]) -> str:
    return "-".join(
        f"{int(part):04d}" if i == 0 else f"{int(part):02d}" for i, part in enumerate(parts)
    )


class SqlAlchemyIncomeSummaryRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def _incomes(self, user_id: int, filters: IncomeSummaryFilters) -> Subquery:
        branches = []
        for kind, model, _tag_table in _TABLES:
            if filters.kind is not None and filters.kind != kind:
                continue
            conditions = [model.user_id == user_id]
            if filters.start_date is not None:
                conditions.append(model.recorded_on >= filters.start_date)
            if filters.end_date is not None:
                conditions.append(model.recorded_on <= filters.end_date)
            if filters.source_ids:
                conditions.append(model.source_id.in_(filters.source_ids))
            if filters.subcategory_ids:
                conditions.append(model.subcategory_id.in_(filters.subcategory_ids))
            if filters.tag_ids:
                conditions.append(model.tags.any(Tag.id.in_(filters.tag_ids)))
            branches.append(
                select(
                    model.id.label("id"),
                    literal(kind, String).label("kind"),
                    model.source_id.label("source_id"),
                    model.subcategory_id.label("subcategory_id"),
                    model.amount.label("amount"),
                    model.recorded_on.label("recorded_on"),
                ).where(*conditions)
            )
        query = branches[0] if len(branches) == 1 else union_all(*branches)
        return query.subquery("incomes")

    def _tag_pairs(self) -> Subquery:
        """(id del ingreso, kind, tag_id) de ambas tablas de tags."""
        return union_all(
            *(
                select(
                    tag_table.income_id.label("id"),
                    literal(kind, String).label("kind"),
                    tag_table.tag_id.label("tag_id"),
                )
                for kind, _model, tag_table in _TABLES
            )
        ).subquery("income_tags")

    def summarize(
        self,
        *,
        user_id: int,
        group_by: IncomeGroupBy,
        stack_by: IncomeStack | None,
        filters: IncomeSummaryFilters,
    ) -> tuple[Sequence[IncomeSummaryRow], IncomeTotals]:
        incomes = self._incomes(user_id, filters)
        total_amount = func.sum(incomes.c.amount)
        count = func.count(incomes.c.id)

        if group_by == "source":
            result = self._db.execute(
                select(IncomeSource.id, IncomeSource.name, total_amount, count)
                .join(IncomeSource, IncomeSource.id == incomes.c.source_id)
                .group_by(IncomeSource.id, IncomeSource.name)
                .order_by(total_amount.desc())
            )
            rows = [
                IncomeSummaryRow(str(id_), name, None, None, total, n)
                for id_, name, total, n in result
            ]
        elif group_by == "subcategory":
            result = self._db.execute(
                select(
                    IncomeSubcategory.id,
                    IncomeSubcategory.name,
                    IncomeSource.name,
                    total_amount,
                    count,
                )
                .join(IncomeSubcategory, IncomeSubcategory.id == incomes.c.subcategory_id)
                .join(IncomeSource, IncomeSource.id == IncomeSubcategory.source_id)
                .group_by(IncomeSubcategory.id, IncomeSubcategory.name, IncomeSource.name)
                .order_by(total_amount.desc())
            )
            rows = [
                IncomeSummaryRow(str(id_), name, parent, None, total, n)
                for id_, name, parent, total, n in result
            ]
        elif group_by == "tag":
            # LEFT JOIN: los ingresos sin tag quedan en un grupo propio en vez
            # de desaparecer (mismo criterio que el resumen de gastos).
            pairs = self._tag_pairs()
            result = self._db.execute(
                select(Tag.id, Tag.name, Tag.color_key, total_amount, count)
                .select_from(incomes)
                .outerjoin(pairs, and_(pairs.c.id == incomes.c.id, pairs.c.kind == incomes.c.kind))
                .outerjoin(Tag, Tag.id == pairs.c.tag_id)
                .group_by(Tag.id, Tag.name, Tag.color_key)
                .order_by(total_amount.desc())
            )
            rows = [
                IncomeSummaryRow(
                    str(id_) if id_ is not None else "none",
                    name if name is not None else "Untagged",
                    None,
                    color,
                    total,
                    n,
                )
                for id_, name, color, total, n in result
            ]
        else:
            rows = self._summarize_periods(incomes, group_by, stack_by)

        is_direct = incomes.c.kind == "direct"
        grand_total, grand_count, direct_total, interest_total = self._db.execute(
            select(
                func.coalesce(total_amount, 0),
                count,
                func.coalesce(func.sum(case((is_direct, incomes.c.amount), else_=0)), 0),
                func.coalesce(func.sum(case((is_direct, 0), else_=incomes.c.amount)), 0),
            )
        ).one()
        return rows, IncomeTotals(
            Decimal(grand_total), grand_count, Decimal(direct_total), Decimal(interest_total)
        )

    def _summarize_periods(
        self, incomes: Subquery, group_by: IncomeGroupBy, stack_by: IncomeStack | None
    ) -> list[IncomeSummaryRow]:
        # extract() en vez de date_trunc: funciona igual en Postgres y en el
        # SQLite de los tests.
        year = extract("year", incomes.c.recorded_on)
        period = [year] if group_by == "year" else [year, extract("month", incomes.c.recorded_on)]
        total_amount = func.sum(incomes.c.amount)
        count = func.count(incomes.c.id)

        if stack_by is None:
            result = self._db.execute(
                select(*period, total_amount, count).group_by(*period).order_by(*period)
            )
            rows = []
            for row in result:
                *parts, total, n = row
                key = _period_key(parts)
                rows.append(IncomeSummaryRow(key, key, None, None, total, n))
            return rows

        catalog = IncomeSource if stack_by == "source" else IncomeSubcategory
        fk = incomes.c.source_id if stack_by == "source" else incomes.c.subcategory_id
        result = self._db.execute(
            select(*period, catalog.id, catalog.name, total_amount, count)
            .join(catalog, catalog.id == fk)
            .group_by(*period, catalog.id, catalog.name)
            .order_by(*period, total_amount.desc())
        )
        rows = []
        for row in result:
            *parts, segment_id, segment_name, total, n = row
            key = _period_key(parts)
            rows.append(
                IncomeSummaryRow(key, key, None, None, total, n, str(segment_id), segment_name)
            )
        return rows
