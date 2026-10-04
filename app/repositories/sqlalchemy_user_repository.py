"""Implementacion del UserRepository sobre SQLAlchemy/Postgres."""

from collections.abc import Sequence

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.db.models.user import User, UserIdentity


class SqlAlchemyUserRepository:
    def __init__(self, db: Session) -> None:
        self._db = db

    def get(self, user_id: int) -> User | None:
        return self._db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        # lower() tambien del lado de la columna: es la expresion del indice
        # unico (uq_users_email), asi que Postgres lo usa para esta busqueda.
        return self._db.execute(
            select(User).where(func.lower(User.email) == email)
        ).scalar_one_or_none()

    def get_by_username(self, username: str) -> User | None:
        # Misma expresion que el indice unico uq_users_username.
        return self._db.execute(
            select(User).where(func.lower(User.username) == username)
        ).scalar_one_or_none()

    def list_all(self) -> Sequence[User]:
        return self._db.execute(select(User).order_by(User.id)).scalars().all()

    def add(self, user: User) -> None:
        self._db.add(user)

    def get_identity(self, provider: str, provider_subject: str) -> UserIdentity | None:
        return self._db.execute(
            select(UserIdentity).where(
                UserIdentity.provider == provider,
                UserIdentity.provider_subject == provider_subject,
            )
        ).scalar_one_or_none()

    def has_identities(self, user_id: int) -> bool:
        return bool(self._db.scalar(select(exists().where(UserIdentity.user_id == user_id))))

    def add_identity(self, identity: UserIdentity) -> None:
        self._db.add(identity)

    def flush(self) -> None:
        self._db.flush()
