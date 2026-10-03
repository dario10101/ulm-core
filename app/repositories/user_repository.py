"""Interfaz (Protocol) del acceso a datos de usuarios y sus identidades."""

from collections.abc import Sequence
from typing import Protocol

from app.db.models.user import User, UserIdentity


class UserRepository(Protocol):
    def get(self, user_id: int) -> User | None: ...

    def get_by_email(self, email: str) -> User | None:
        """`email` ya normalizado (ver app.services.user_admin_service.normalize_email)."""
        ...

    def list_all(self) -> Sequence[User]: ...

    def add(self, user: User) -> None: ...

    def get_identity(self, provider: str, provider_subject: str) -> UserIdentity | None: ...

    def has_identities(self, user_id: int) -> bool: ...

    def add_identity(self, identity: UserIdentity) -> None: ...

    def flush(self) -> None:
        """Manda los INSERT/UPDATE pendientes a la base sin cerrar la
        transaccion. Sirve para obtener los ids autogenerados; el commit lo
        hace `get_db` al final del request."""
        ...
