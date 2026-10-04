"""Implementacion del CldUserEventRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistCategory
from app.db.models.cld_user_event import CldUserEvent
from app.schemas.checklist import CategoryStatus


class SqlAlchemyCldUserEventRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_in_range(
        self, user_id: int, range_start: date, range_end: date
    ) -> Sequence[CldUserEvent]:
        return (
            self._db.execute(
                select(CldUserEvent)
                .join(ChecklistCategory, CldUserEvent.category_id == ChecklistCategory.id)
                .where(
                    CldUserEvent.user_id == user_id,
                    CldUserEvent.first_day <= range_end,
                    CldUserEvent.last_day >= range_start,
                    ChecklistCategory.status == CategoryStatus.ENABLED.value,
                )
            )
            .scalars()
            .all()
        )

    def list_codes(self, *, user_id: int) -> list[str]:
        return list(
            self._db.execute(
                select(CldUserEvent.code)
                .where(CldUserEvent.user_id == user_id)
                .distinct()
                .order_by(CldUserEvent.code)
            )
            .scalars()
            .all()
        )

    def get(self, event_id: int, *, user_id: int) -> CldUserEvent | None:
        return self._db.execute(
            select(CldUserEvent).where(CldUserEvent.id == event_id, CldUserEvent.user_id == user_id)
        ).scalar_one_or_none()

    def add(self, event: CldUserEvent) -> None:
        self._db.add(event)

    def delete(self, event: CldUserEvent) -> None:
        self._db.delete(event)

    def flush(self) -> None:
        self._db.flush()
