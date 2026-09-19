"""Implementacion del TaskRepository sobre SQLAlchemy/Postgres."""

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistTask


class SqlAlchemyTaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_week(self, week_id: int) -> Sequence[ChecklistTask]:
        return (
            self._db.execute(
                select(ChecklistTask)
                .where(ChecklistTask.cl_week_id == week_id)
                .order_by(ChecklistTask.day_of_week, ChecklistTask.id)
            )
            .scalars()
            .all()
        )

    def get(self, task_id: int) -> ChecklistTask | None:
        return self._db.get(ChecklistTask, task_id)

    def add(self, task: ChecklistTask) -> None:
        self._db.add(task)

    def commit(self) -> None:
        self._db.commit()

    def refresh(self, task: ChecklistTask) -> None:
        self._db.refresh(task)
