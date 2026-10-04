"""Implementacion del CldEventRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models.cld_event import CldEvent


class SqlAlchemyCldEventRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_in_range(self, range_start: date, range_end: date) -> Sequence[CldEvent]:
        # Solapamiento de intervalos: el evento empieza antes de que termine el
        # rango, y termina despues de que el rango empieza.
        return (
            self._db.execute(
                select(CldEvent)
                .where(CldEvent.first_day <= range_end, CldEvent.last_day >= range_start)
                .order_by(CldEvent.first_day, CldEvent.id)
            )
            .scalars()
            .all()
        )

    def get(self, event_id: int) -> CldEvent | None:
        return self._db.get(CldEvent, event_id)

    def add(self, event: CldEvent) -> None:
        self._db.add(event)

    def delete(self, event: CldEvent) -> None:
        self._db.delete(event)

    def flush(self) -> None:
        self._db.flush()
