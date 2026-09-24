"""Implementacion del CldTaskRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistCategory
from app.db.models.cld_task import CldTask
from app.schemas.checklist import CategoryStatus


class SqlAlchemyCldTaskRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_sync_enabled(self, user_id: int) -> Sequence[CldTask]:
        # Una tarea bajo una categoria DISABLED no debe generar tareas nuevas
        # en checklists futuros (mismo criterio que el template).
        return (
            self._db.execute(
                select(CldTask)
                .join(ChecklistCategory, CldTask.category_id == ChecklistCategory.id)
                .where(
                    CldTask.user_id == user_id,
                    CldTask.add_to_checklist.is_(True),
                    ChecklistCategory.status == CategoryStatus.ENABLED.value,
                )
            )
            .scalars()
            .all()
        )

    def list_by_user(self, user_id: int) -> Sequence[CldTask]:
        # Solo tareas de categorias ENABLED: una categoria deshabilitada
        # deja de aparecer en el calendario.
        return (
            self._db.execute(
                select(CldTask)
                .join(ChecklistCategory, CldTask.category_id == ChecklistCategory.id)
                .where(
                    CldTask.user_id == user_id,
                    ChecklistCategory.status == CategoryStatus.ENABLED.value,
                )
                .order_by(CldTask.id)
            )
            .scalars()
            .all()
        )

    def get(self, task_id: int) -> CldTask | None:
        return self._db.get(CldTask, task_id)

    def flush(self) -> None:
        self._db.flush()

    def add(self, task: CldTask) -> None:
        self._db.add(task)

    def delete(self, task: CldTask) -> None:
        self._db.delete(task)
