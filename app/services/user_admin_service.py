"""Administracion de usuarios: invitar, cambiar email, deshabilitar.

Es el unico lugar que crea filas en `users` (ver `register`): lo usan el
script scripts/manage_users.py, el login en modo `open` y, mas adelante, la
pantalla de administracion. Un solo camino de creacion evita que cada entrada
aplique reglas distintas (normalizacion del email, unicidad, defaults).
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.db.models.user import User
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.errors import EmailTakenError, UserNotFoundError


def normalize_email(email: str) -> str:
    """Minusculas y sin espacios: es la forma en que se guarda y se busca.
    El indice unico (uq_users_email) es sobre lower(email), asi que esto y la
    base coinciden en que es "el mismo email"."""
    return email.strip().lower()


def valid_timezone(name: str | None) -> str | None:
    """`name` si es una zona IANA conocida, None si no (viene del navegador,
    no se confia en el)."""
    if not name:
        return None
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return None
    return name


class UserAdminService:
    def __init__(self, users: UserRepository, sessions: UserSessionRepository) -> None:
        self._users = users
        self._sessions = sessions

    def register(self, *, email: str, name: str | None, timezone: str | None) -> User:
        email = normalize_email(email)
        if self._users.get_by_email(email) is not None:
            raise EmailTakenError(email)
        user = User(
            email=email,
            # Placeholder hasta el primer login, que lo reemplaza por el
            # nombre de la cuenta de Google si no se dio uno.
            name=name or email.split("@")[0],
            timezone=valid_timezone(timezone) or settings.default_timezone,
        )
        self._users.add(user)
        self._users.flush()
        return user

    def invite(self, email: str, *, name: str | None = None) -> User:
        """Crea el usuario sin identidad: el primer login con Google con este
        email lo vincula. La zona horaria la fija ese primer login."""
        return self.register(email=email, name=name, timezone=None)

    def set_email(self, user_id: int, email: str) -> User:
        user = self._get(user_id)
        email = normalize_email(email)
        other = self._users.get_by_email(email)
        if other is not None and other.id != user.id:
            raise EmailTakenError(email)
        user.email = email
        self._users.flush()
        return user

    def disable(self, user_id: int) -> User:
        """Corta el acceso ya mismo (cierra sus sesiones) y conserva los datos."""
        user = self._get(user_id)
        user.disabled_at = datetime.now(UTC)
        self._sessions.delete_all_for_user(user.id)
        self._users.flush()
        return user

    def enable(self, user_id: int) -> User:
        user = self._get(user_id)
        user.disabled_at = None
        self._users.flush()
        return user

    def get_by_email(self, email: str) -> User:
        user = self._users.get_by_email(normalize_email(email))
        if user is None:
            raise UserNotFoundError(email)
        return user

    def list_users(self) -> Sequence[User]:
        return self._users.list_all()

    def has_logged_in(self, user_id: int) -> bool:
        return self._users.has_identities(user_id)

    def _get(self, user_id: int) -> User:
        user = self._users.get(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user
