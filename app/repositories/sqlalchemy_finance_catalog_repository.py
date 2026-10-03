"""Implementacion del FinanceCatalogRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.finance import Category, IncomeSource, IncomeSubcategory, PaymentMethod, Tag
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
