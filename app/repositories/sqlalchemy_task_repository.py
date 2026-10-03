"""Implementacion del TaskRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistCategory, ChecklistTask
from app.schemas.checklist import CategoryStatus


class SqlAlchemyTaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_week(self, week_id: int, *, user_id: int) -> Sequence[ChecklistTask]:
        return (
            self._db.execute(
                select(ChecklistTask)
                .where(ChecklistTask.cl_week_id == week_id, ChecklistTask.user_id == user_id)
                .order_by(ChecklistTask.day_of_week, ChecklistTask.id)
            )
            .scalars()
            .all()
        )

    def list_visible_by_week(self, week_id: int, *, user_id: int) -> Sequence[ChecklistTask]:
        return (
            self._db.execute(
                select(ChecklistTask)
                .join(ChecklistCategory, ChecklistTask.category_id == ChecklistCategory.id)
                .where(
                    ChecklistTask.cl_week_id == week_id,
                    ChecklistTask.user_id == user_id,
                    ChecklistCategory.status == CategoryStatus.ENABLED.value,
                )
                .order_by(ChecklistTask.day_of_week, ChecklistTask.id)
            )
            .scalars()
            .all()
        )

    def get(self, task_id: int, *, user_id: int) -> ChecklistTask | None:
        return self._db.execute(
            select(ChecklistTask).where(
                ChecklistTask.id == task_id, ChecklistTask.user_id == user_id
            )
        ).scalar_one_or_none()

    def flush(self) -> None:
        self._db.flush()

    def add(self, task: ChecklistTask) -> None:
        self._db.add(task)

    def delete(self, task: ChecklistTask) -> None:
        self._db.delete(task)
