"""Implementacion del WeekCategoryDayScoreRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistWeekCategoryDayScore


class SqlAlchemyWeekCategoryDayScoreRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, row: ChecklistWeekCategoryDayScore) -> None:
        self._db.add(row)

    def list_by_week_ids(self, week_ids: Sequence[int]) -> Sequence[ChecklistWeekCategoryDayScore]:
        if not week_ids:
            return []
        return (
            self._db.execute(
                select(ChecklistWeekCategoryDayScore).where(
                    ChecklistWeekCategoryDayScore.cl_week_id.in_(week_ids)
                )
            )
            .scalars()
            .all()
        )
