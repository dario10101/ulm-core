"""Implementacion del WeightRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models.weight import WeightRecord


class SqlAlchemyWeightRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self, *, user_id: int, weight_kg: Decimal, recorded_on: date, note: str | None
    ) -> WeightRecord:
        record = WeightRecord(
            user_id=user_id, weight_kg=weight_kg, recorded_on=recorded_on, note=note
        )
        self._db.add(record)
        self._db.flush()
        return record

    def list(
        self,
        *,
        user_id: int,
        start_date: date | None,
        end_date: date | None,
        offset: int,
        limit: int,
    ) -> tuple[Sequence[WeightRecord], int]:
        conditions = [WeightRecord.user_id == user_id]
        if start_date is not None:
            conditions.append(WeightRecord.recorded_on >= start_date)
        if end_date is not None:
            conditions.append(WeightRecord.recorded_on <= end_date)

        total = self._db.scalar(select(func.count()).select_from(WeightRecord).where(*conditions))

        items = (
            self._db.execute(
                select(WeightRecord)
                .where(*conditions)
                .order_by(WeightRecord.recorded_on.desc(), WeightRecord.id.desc())
                .offset(offset)
                .limit(limit)
            )
            .scalars()
            .all()
        )
        return items, total or 0

    def get(self, weight_id: int) -> WeightRecord | None:
        return self._db.get(WeightRecord, weight_id)

    def update(
        self,
        weight_id: int,
        *,
        user_id: int,
        weight_kg: Decimal,
        recorded_on: date,
        note: str | None,
    ) -> WeightRecord | None:
        record = self._db.get(WeightRecord, weight_id)
        if record is None or record.user_id != user_id:
            return None

        record.weight_kg = weight_kg
        record.recorded_on = recorded_on
        record.note = note
        record.updated_at = datetime.now(UTC)
        self._db.flush()
        return record

    def delete(self, weight_id: int, *, user_id: int) -> bool:
        record = self._db.get(WeightRecord, weight_id)
        if record is None or record.user_id != user_id:
            return False

        self._db.delete(record)
        self._db.flush()
        return True
