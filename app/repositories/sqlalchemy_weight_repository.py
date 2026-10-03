"""Implementacion del WeightRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import extract, func, select
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

    def summarize(
        self,
        *,
        user_id: int,
        group_by: str,
        start_date: date | None,
        end_date: date | None,
    ) -> Sequence[tuple[str, Decimal, int]]:
        conditions = [WeightRecord.user_id == user_id]
        if start_date is not None:
            conditions.append(WeightRecord.recorded_on >= start_date)
        if end_date is not None:
            conditions.append(WeightRecord.recorded_on <= end_date)

        # extract() en vez de date_trunc: funciona igual en Postgres y en el
        # SQLite de los tests (mismo criterio que el resumen de gastos).
        if group_by == "day":
            period = [WeightRecord.recorded_on]
        else:
            period = [
                extract("year", WeightRecord.recorded_on),
                extract("month", WeightRecord.recorded_on),
            ]
        result = self._db.execute(
            select(*period, func.avg(WeightRecord.weight_kg), func.count(WeightRecord.id))
            .where(*conditions)
            .group_by(*period)
            .order_by(*period)
        )
        rows: list[tuple[str, Decimal, int]] = []
        for row in result:
            *parts, average, count = row
            if group_by == "day":
                key = str(parts[0])
            else:
                key = f"{int(parts[0]):04d}-{int(parts[1]):02d}"
            rows.append((key, Decimal(str(average)), count))
        return rows

    def list_years(self, *, user_id: int) -> Sequence[int]:
        year = extract("year", WeightRecord.recorded_on)
        result = self._db.execute(
            select(year).where(WeightRecord.user_id == user_id).group_by(year).order_by(year.desc())
        )
        return [int(value) for value in result.scalars()]

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
