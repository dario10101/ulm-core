"""Implementacion del TemplateTaskRepository sobre SQLAlchemy/Postgres."""

from typing import Sequence

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistCategory, ChecklistTemplateTask


class SqlAlchemyTemplateTaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_user(self, user_id: int) -> Sequence[ChecklistTemplateTask]:
        return (
            self._db.execute(
                select(ChecklistTemplateTask)
                .join(ChecklistCategory, ChecklistTemplateTask.category_id == ChecklistCategory.id)
                .where(ChecklistCategory.user_id == user_id)
                .order_by(ChecklistTemplateTask.id)
            )
            .scalars()
            .all()
        )

    def get(self, task_id: int) -> ChecklistTemplateTask | None:
        return self._db.get(ChecklistTemplateTask, task_id)

    def add(self, task: ChecklistTemplateTask) -> None:
        self._db.add(task)

    def delete(self, task: ChecklistTemplateTask) -> None:
        self._db.delete(task)

    def category_belongs_to_user(self, category_id: int, user_id: int) -> bool:
        return bool(
            self._db.scalar(
                select(
                    exists().where(
                        ChecklistCategory.id == category_id,
                        ChecklistCategory.user_id == user_id,
                    )
                )
            )
        )

    def commit(self) -> None:
        self._db.commit()

    def refresh(self, task: ChecklistTemplateTask) -> None:
        self._db.refresh(task)
