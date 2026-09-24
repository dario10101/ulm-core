"""Implementacion del CategoryRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import case, exists, select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistCategory, ChecklistTemplateTask
from app.schemas.checklist import CategoryStatus


class SqlAlchemyCategoryRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_user(self, user_id: int) -> Sequence[ChecklistCategory]:
        return (
            self._db.execute(
                select(ChecklistCategory)
                .where(
                    ChecklistCategory.user_id == user_id,
                    ChecklistCategory.status == CategoryStatus.ENABLED.value,
                )
                .order_by(ChecklistCategory.priority)
            )
            .scalars()
            .all()
        )

    def list_by_ids(self, user_id: int, category_ids: Sequence[int]) -> Sequence[ChecklistCategory]:
        if not category_ids:
            return []
        return (
            self._db.execute(
                select(ChecklistCategory).where(
                    ChecklistCategory.user_id == user_id,
                    ChecklistCategory.id.in_(category_ids),
                )
            )
            .scalars()
            .all()
        )

    def list_all_by_user(self, user_id: int) -> Sequence[ChecklistCategory]:
        # DISABLED siempre al final, sin importar su priority; adentro de cada
        # grupo se ordena por priority.
        status_rank = case((ChecklistCategory.status == CategoryStatus.ENABLED.value, 0), else_=1)
        return (
            self._db.execute(
                select(ChecklistCategory)
                .where(ChecklistCategory.user_id == user_id)
                .order_by(status_rank, ChecklistCategory.priority)
            )
            .scalars()
            .all()
        )

    def get(self, category_id: int) -> ChecklistCategory | None:
        return self._db.get(ChecklistCategory, category_id)

    def flush(self) -> None:
        self._db.flush()

    def add(self, category: ChecklistCategory) -> None:
        self._db.add(category)

    def disable(self, category: ChecklistCategory) -> None:
        category.status = CategoryStatus.DISABLED.value

    def enable(self, category: ChecklistCategory, priority: int) -> None:
        category.status = CategoryStatus.ENABLED.value
        category.priority = priority

    def has_template_tasks(self, category_id: int) -> bool:
        return bool(
            self._db.scalar(
                select(exists().where(ChecklistTemplateTask.category_id == category_id))
            )
        )
