"""Implementacion del UserPermissionRepository sobre SQLAlchemy/Postgres."""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db.models.user import UserPermission


class SqlAlchemyUserPermissionRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def list_for_user(self, user_id: int) -> set[str]:
        return set(
            self._db.execute(
                select(UserPermission.permission).where(UserPermission.user_id == user_id)
            ).scalars()
        )

    def add(self, user_id: int, permission: str, *, granted_by: int | None) -> None:
        if self._db.get(UserPermission, (user_id, permission)) is None:
            self._db.add(
                UserPermission(user_id=user_id, permission=permission, granted_by=granted_by)
            )
            self._db.flush()

    def remove(self, user_id: int, permission: str) -> None:
        self._db.execute(
            delete(UserPermission).where(
                UserPermission.user_id == user_id, UserPermission.permission == permission
            )
        )
