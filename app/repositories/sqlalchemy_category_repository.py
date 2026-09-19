"""Implementacion del CategoryRepository sobre SQLAlchemy/Postgres."""

from typing import Sequence

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistCategory, ChecklistTemplateTask


class SqlAlchemyCategoryRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_user(self, user_id: int) -> Sequence[ChecklistCategory]:
        return (
            self._db.execute(
                select(ChecklistCategory)
                .where(ChecklistCategory.user_id == user_id)
                .order_by(ChecklistCategory.priority)
            )
            .scalars()
            .all()
        )

    def get(self, category_id: int) -> ChecklistCategory | None:
        return self._db.get(ChecklistCategory, category_id)

    def add(self, category: ChecklistCategory) -> None:
        self._db.add(category)

    def delete(self, category: ChecklistCategory) -> None:
        self._db.delete(category)

    def has_template_tasks(self, category_id: int) -> bool:
        return bool(
            self._db.scalar(
                select(
                    exists().where(ChecklistTemplateTask.category_id == category_id)
                )
            )
        )

    def commit(self) -> None:
        self._db.commit()

    def refresh(self, category: ChecklistCategory) -> None:
        self._db.refresh(category)
