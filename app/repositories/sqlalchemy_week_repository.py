"""Implementacion del WeekRepository sobre SQLAlchemy/Postgres."""

from datetime import date
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.checklist import ChecklistWeek


class SqlAlchemyWeekRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get_current_open(self, user_id: int) -> ChecklistWeek | None:
        return self._db.execute(
            select(ChecklistWeek)
            .where(ChecklistWeek.user_id == user_id, ChecklistWeek.closed.is_(False))
            .order_by(ChecklistWeek.first_day.desc(), ChecklistWeek.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get_latest(self, user_id: int) -> ChecklistWeek | None:
        return self._db.execute(
            select(ChecklistWeek)
            .where(ChecklistWeek.user_id == user_id)
            .order_by(ChecklistWeek.last_day.desc(), ChecklistWeek.id.desc())
            .limit(1)
        ).scalar_one_or_none()

    def get(self, week_id: int) -> ChecklistWeek | None:
        return self._db.get(ChecklistWeek, week_id)

    def add(self, week: ChecklistWeek) -> None:
        self._db.add(week)

    def list_closed_by_year(self, user_id: int, year: int) -> Sequence[ChecklistWeek]:
        year_start, year_end = date(year, 1, 1), date(year, 12, 31)
        return (
            self._db.execute(
                select(ChecklistWeek)
                .where(
                    ChecklistWeek.user_id == user_id,
                    ChecklistWeek.closed.is_(True),
                    ChecklistWeek.first_day >= year_start,
                    ChecklistWeek.first_day <= year_end,
                )
                .order_by(ChecklistWeek.first_day)
            )
            .scalars()
            .all()
        )

    def list_closed_overlapping_year(self, user_id: int, year: int) -> Sequence[ChecklistWeek]:
        year_start, year_end = date(year, 1, 1), date(year, 12, 31)
        return (
            self._db.execute(
                select(ChecklistWeek)
                .where(
                    ChecklistWeek.user_id == user_id,
                    ChecklistWeek.closed.is_(True),
                    ChecklistWeek.first_day <= year_end,
                    ChecklistWeek.last_day >= year_start,
                )
                .order_by(ChecklistWeek.first_day)
            )
            .scalars()
            .all()
        )

    def commit(self) -> None:
        self._db.commit()

    def refresh(self, week: ChecklistWeek) -> None:
        self._db.refresh(week)
