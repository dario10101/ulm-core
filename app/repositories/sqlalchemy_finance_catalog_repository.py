"""Implementacion del FinanceCatalogRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.finance import Category, PaymentMethod, Tag
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
