"""Implementacion del MealRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.meal import Meal


class SqlAlchemyMealRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        user_id: int,
        recorded_on: datetime,
        meal_type: str,
        meal_size: int,
        meal_content: str | None,
        drink: str | None,
        note: str | None,
    ) -> Meal:
        record = Meal(
            user_id=user_id,
            recorded_on=recorded_on,
            meal_type=meal_type,
            meal_size=meal_size,
            meal_content=meal_content,
            drink=drink,
            note=note,
        )
        self._db.add(record)
        self._db.flush()
        return record

    def list(
        self,
        *,
        user_id: int,
        start_at: datetime | None,
        end_at: datetime | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[Meal], int]:
        conditions = [Meal.user_id == user_id]
        if start_at is not None:
            conditions.append(Meal.recorded_on >= start_at)
        if end_at is not None:
            conditions.append(Meal.recorded_on <= end_at)

        total = self._db.scalar(select(func.count()).select_from(Meal).where(*conditions))

        items = (
            self._db.execute(
                select(Meal)
                .where(*conditions)
                .order_by(Meal.recorded_on.desc(), Meal.id.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total or 0

    def get(self, meal_id: int) -> Meal | None:
        return self._db.get(Meal, meal_id)

    def update(
        self,
        meal_id: int,
        *,
        user_id: int,
        recorded_on: datetime,
        meal_type: str,
        meal_size: int,
        meal_content: str | None,
        drink: str | None,
        note: str | None,
    ) -> Meal | None:
        record = self._db.get(Meal, meal_id)
        if record is None or record.user_id != user_id:
            return None

        record.recorded_on = recorded_on
        record.meal_type = meal_type
        record.meal_size = meal_size
        record.meal_content = meal_content
        record.drink = drink
        record.note = note
        record.updated_at = datetime.now(UTC)
        self._db.flush()
        return record

    def delete(self, meal_id: int, *, user_id: int) -> bool:
        record = self._db.get(Meal, meal_id)
        if record is None or record.user_id != user_id:
            return False

        self._db.delete(record)
        self._db.flush()
        return True
