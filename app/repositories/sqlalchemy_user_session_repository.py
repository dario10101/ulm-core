"""Implementacion del UserSessionRepository sobre SQLAlchemy/Postgres."""

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.user import UserSession


class SqlAlchemyUserSessionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def add(self, session: UserSession) -> None:
        self._db.add(session)

    def get_by_token_hash(self, token_hash: str) -> UserSession | None:
        return self._db.execute(
            select(UserSession).where(UserSession.token_hash == token_hash)
        ).scalar_one_or_none()

    def delete(self, session: UserSession) -> None:
        self._db.delete(session)

    def delete_expired_for_user(self, user_id: int, now: datetime) -> None:
        self._db.execute(
            delete(UserSession).where(UserSession.user_id == user_id, UserSession.expires_at <= now)
        )

    def delete_all_for_user(self, user_id: int) -> None:
        self._db.execute(delete(UserSession).where(UserSession.user_id == user_id))

    def flush(self) -> None:
        self._db.flush()
