"""Interfaz (Protocol) del acceso a datos de sesiones de login."""

from datetime import datetime
from typing import Protocol

from app.db.models.user import UserSession


class UserSessionRepository(Protocol):
    def add(self, session: UserSession) -> None: ...

    def get_by_token_hash(self, token_hash: str) -> UserSession | None: ...

    def delete(self, session: UserSession) -> None: ...

    def delete_expired_for_user(self, user_id: int, now: datetime) -> None: ...

    def delete_all_for_user(self, user_id: int) -> None:
        """Cierra todas las sesiones del usuario (ej. al deshabilitarlo)."""
        ...

    def flush(self) -> None: ...
