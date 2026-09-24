"""Implementacion del TemplateTaskRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistCategory, ChecklistTemplateTask
from app.schemas.checklist import CategoryStatus


class SqlAlchemyTemplateTaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_by_user(self, user_id: int) -> Sequence[ChecklistTemplateTask]:
        return (
            self._db.execute(
                select(ChecklistTemplateTask)
                .join(ChecklistCategory, ChecklistTemplateTask.category_id == ChecklistCategory.id)
                .where(
                    ChecklistTemplateTask.user_id == user_id,
                    ChecklistCategory.status == CategoryStatus.ENABLED.value,
                )
                .order_by(ChecklistTemplateTask.id)
            )
            .scalars()
            .all()
        )

    def get(self, task_id: int) -> ChecklistTemplateTask | None:
        return self._db.get(ChecklistTemplateTask, task_id)

    def flush(self) -> None:
        self._db.flush()

    def add(self, task: ChecklistTemplateTask) -> None:
        self._db.add(task)

    def delete(self, task: ChecklistTemplateTask) -> None:
        self._db.delete(task)

    def category_belongs_to_user(self, category_id: int, user_id: int) -> bool:
        # Una categoria DISABLED no puede recibir tareas de template nuevas ni
        # editadas. Las categorias que se llegan a deshabilitar nunca tienen
        # template tasks vivas (replace_categories lo garantiza antes de
        # deshabilitar), asi que esto no bloquea tareas existentes.
        return bool(
            self._db.scalar(
                select(
                    exists().where(
                        ChecklistCategory.id == category_id,
                        ChecklistCategory.user_id == user_id,
                        ChecklistCategory.status == CategoryStatus.ENABLED.value,
                    )
                )
            )
        )
