"""Implementacion del AiUsageRepository sobre SQLAlchemy/Postgres."""

from sqlalchemy.orm import Session

from app.db.models.ai_usage import AiUsageEvent


class SqlAlchemyAiUsageRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, event: AiUsageEvent) -> None:
        self._db.add(event)
        self._db.flush()
