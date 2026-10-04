"""Implementacion del FinanceCatalogRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.base_class import Base
from app.db.models.finance import (
    Category,
    DirectIncome,
    DirectIncomeTag,
    Expense,
    ExpenseTag,
    IncomeSource,
    IncomeSubcategory,
    InterestIncome,
    InterestIncomeTag,
    PaymentMethod,
    Tag,
)
from app.schemas.finance import CatalogStatus


class SqlAlchemyFinanceCatalogRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_enabled_categories(self) -> Sequence[Category]:
        return (
            self._db.execute(
                select(Category)
                .where(Category.status == CatalogStatus.ENABLED.value)
                .order_by(Category.name)
            )
            .scalars()
            .all()
        )

    def list_enabled_payment_methods(self) -> Sequence[PaymentMethod]:
        return (
            self._db.execute(
                select(PaymentMethod)
                .where(PaymentMethod.status == CatalogStatus.ENABLED.value)
                .order_by(PaymentMethod.name)
            )
            .scalars()
            .all()
        )

    def list_enabled_tags(self, user_id: int) -> Sequence[Tag]:
        return (
            self._db.execute(
                select(Tag)
                .where(Tag.user_id == user_id, Tag.status == CatalogStatus.ENABLED.value)
                .order_by(Tag.name)
            )
            .scalars()
            .all()
        )

    def get_category(self, category_id: int) -> Category | None:
        return self._db.get(Category, category_id)

    def get_payment_method(self, payment_method_id: int) -> PaymentMethod | None:
        return self._db.get(PaymentMethod, payment_method_id)

    def list_tags_by_ids(self, user_id: int, tag_ids: Sequence[int]) -> Sequence[Tag]:
        if not tag_ids:
            return []
        return (
            self._db.execute(select(Tag).where(Tag.user_id == user_id, Tag.id.in_(tag_ids)))
            .scalars()
            .all()
        )

    def list_income_sources(self, user_id: int) -> Sequence[IncomeSource]:
        return (
            self._db.execute(
                select(IncomeSource)
                .where(IncomeSource.user_id == user_id)
                .order_by(IncomeSource.id)
            )
            .scalars()
            .all()
        )

    def list_income_subcategories(self, user_id: int) -> Sequence[IncomeSubcategory]:
        # Por id y no por nombre: el formulario usa la primera como default
        # (ej. "SALARIO BASE"), y ese orden lo decide quien la creo primero.
        return (
            self._db.execute(
                select(IncomeSubcategory)
                .where(IncomeSubcategory.user_id == user_id)
                .order_by(IncomeSubcategory.id)
            )
            .scalars()
            .all()
        )

    def get_income_source(self, user_id: int, source_id: int) -> IncomeSource | None:
        source = self._db.get(IncomeSource, source_id)
        return source if source is not None and source.user_id == user_id else None

    def get_income_subcategory(self, user_id: int, subcategory_id: int) -> IncomeSubcategory | None:
        subcategory = self._db.get(IncomeSubcategory, subcategory_id)
        return subcategory if subcategory is not None and subcategory.user_id == user_id else None

    # --- Administracion ---

    def list_all_categories(self) -> Sequence[Category]:
        return self._db.execute(select(Category).order_by(Category.name)).scalars().all()

    def list_all_payment_methods(self) -> Sequence[PaymentMethod]:
        return self._db.execute(select(PaymentMethod).order_by(PaymentMethod.name)).scalars().all()

    def list_tags(self, user_id: int) -> Sequence[Tag]:
        return (
            self._db.execute(select(Tag).where(Tag.user_id == user_id).order_by(Tag.name))
            .scalars()
            .all()
        )

    def get_tag(self, user_id: int, tag_id: int) -> Tag | None:
        tag = self._db.get(Tag, tag_id)
        return tag if tag is not None and tag.user_id == user_id else None

    def _count_by(self, column, *where) -> dict[int, int]:
        rows = self._db.execute(select(column, func.count()).where(*where).group_by(column))
        return {item_id: count for item_id, count in rows}

    def category_usage(self) -> dict[int, int]:
        return self._count_by(Expense.category_id)

    def payment_method_usage(self) -> dict[int, int]:
        return self._count_by(Expense.payment_method_id)

    def tag_usage(self, user_id: int) -> dict[int, int]:
        usage: dict[int, int] = {}
        # Las tablas M2M no tienen user_id: se filtra por el dueño del tag.
        for link in (ExpenseTag, DirectIncomeTag, InterestIncomeTag):
            counts = self._count_by(
                link.tag_id, link.tag_id.in_(select(Tag.id).where(Tag.user_id == user_id))
            )
            for tag_id, count in counts.items():
                usage[tag_id] = usage.get(tag_id, 0) + count
        return usage

    def source_usage(self, user_id: int) -> dict[int, tuple[int, int]]:
        direct = self._count_by(DirectIncome.source_id, DirectIncome.user_id == user_id)
        interest = self._count_by(InterestIncome.source_id, InterestIncome.user_id == user_id)
        return {
            source_id: (direct.get(source_id, 0), interest.get(source_id, 0))
            for source_id in direct.keys() | interest.keys()
        }

    def subcategory_usage(self, user_id: int) -> dict[int, int]:
        usage = self._count_by(DirectIncome.subcategory_id, DirectIncome.user_id == user_id)
        interest = self._count_by(InterestIncome.subcategory_id, InterestIncome.user_id == user_id)
        for subcategory_id, count in interest.items():
            usage[subcategory_id] = usage.get(subcategory_id, 0) + count
        return usage

    def add(self, item: Base) -> None:
        self._db.add(item)

    def delete(self, item: Base) -> None:
        self._db.delete(item)

    def flush(self) -> None:
        self._db.flush()
