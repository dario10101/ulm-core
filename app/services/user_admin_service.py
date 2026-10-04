"""Administracion de usuarios: invitar, cambiar email, deshabilitar, permisos.

Es el unico lugar que crea filas en `users` (ver `register`): lo usan el
script scripts/manage_users.py, el login en modo `open` y la pantalla de
administracion (Settings -> Users, rutas /admin/users). Un solo camino de
creacion evita que cada entrada aplique reglas distintas (normalizacion del
email, unicidad, defaults).
"""

from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.config import settings
from app.db.models.user import User
from app.repositories.user_permission_repository import UserPermissionRepository
from app.repositories.user_repository import UserRepository
from app.repositories.user_session_repository import UserSessionRepository
from app.services.errors import (
    AdminRoleNotEditableError,
    EmailTakenError,
    MissingBasePermissionError,
    UnknownPermissionError,
    UserNotFoundError,
)
from app.services.permissions import (
    ALL_PERMISSIONS,
    Permission,
    is_admin_email,
    known_permissions,
)


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


UserStatus = Literal["invited", "active", "disabled"]


class UserAdminService:
    def __init__(
        self,
        users: UserRepository,
        sessions: UserSessionRepository,
        permissions: UserPermissionRepository,
    ) -> None:
        self._users = users
        self._sessions = sessions
        self._permissions = permissions

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
        """Corta el acceso ya mismo (cierra sus sesiones) y conserva los datos.
        Un admin no se deshabilita: se lo saca de ADMIN_EMAILS."""
        user = self._get_editable(user_id)
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

    def status(self, user: User) -> UserStatus:
        """`invited` mientras no haya entrado nunca (sin identidad vinculada)."""
        if user.disabled_at is not None:
            return "disabled"
        return "active" if self.has_logged_in(user.id) else "invited"

    # --- Permisos ---

    @staticmethod
    def is_admin(user: User) -> bool:
        return is_admin_email(user.email)

    def effective_permissions(self, user: User) -> frozenset[Permission]:
        """Lo que el usuario puede usar: todo si es admin, lo asignado si no."""
        if self.is_admin(user):
            return ALL_PERMISSIONS
        return frozenset(known_permissions(self._permissions.list_for_user(user.id)))

    def grant(self, user_id: int, value: str, *, granted_by: int | None) -> frozenset[Permission]:
        user = self._get_editable(user_id)
        permission = self._parse(value)
        base = permission.base
        if base is not None and base.value not in self._permissions.list_for_user(user.id):
            raise MissingBasePermissionError(permission.value, base.value)
        self._permissions.add(user.id, permission.value, granted_by=granted_by)
        return self.effective_permissions(user)

    def set_permissions(
        self, user_id: int, values: Iterable[str], *, granted_by: int | None
    ) -> frozenset[Permission]:
        """Reemplaza el conjunto completo (lo que manda la pantalla de admin).
        Solo toca lo que cambia: un permiso que sigue conserva su granted_by y
        granted_at. A diferencia de `revoke`, no hay cascada: un `.ai` sin su
        base en el mismo conjunto es un error, no algo que se corrija solo."""
        user = self._get_editable(user_id)
        wanted = {self._parse(value) for value in values}
        for permission in wanted:
            base = permission.base
            if base is not None and base not in wanted:
                raise MissingBasePermissionError(permission.value, base.value)

        current = self._permissions.list_for_user(user.id)
        wanted_values = {permission.value for permission in wanted}
        # Tambien limpia valores guardados que ya no estan en el catalogo.
        for value in current - wanted_values:
            self._permissions.remove(user.id, value)
        for value in sorted(wanted_values - current):
            self._permissions.add(user.id, value, granted_by=granted_by)
        return self.effective_permissions(user)

    def revoke(self, user_id: int, value: str) -> frozenset[Permission]:
        """Quitar el base tambien quita su avanzado: `finances.ai` sin
        `finances` no tiene sentido. Acepta un valor fuera del catalogo, para
        poder limpiar uno que quedo de un dominio que ya no existe."""
        user = self._get_editable(user_id)
        self._permissions.remove(user.id, value)
        self._permissions.remove(user.id, f"{value}.ai")
        return self.effective_permissions(user)

    @staticmethod
    def _parse(value: str) -> Permission:
        try:
            return Permission(value)
        except ValueError:
            raise UnknownPermissionError(value) from None

    def _get_editable(self, user_id: int) -> User:
        user = self._get(user_id)
        if self.is_admin(user):
            raise AdminRoleNotEditableError(
                f"{user.email} es admin por ADMIN_EMAILS: no se edita por API ni consola"
            )
        return user

    def get(self, user_id: int) -> User:
        return self._get(user_id)

    def _get(self, user_id: int) -> User:
        user = self._users.get(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return user
