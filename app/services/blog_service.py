"""Lectura publica de blogs (sin sesion).

Por ahora solo resuelve si un username tiene blog. El contenido sigue quemado
en el front; cuando viva en la base (ver PLAN-BLOG.md), este service lo
entregara con las mismas reglas de visibilidad.
"""

from app.db.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.errors import BlogNotFoundError
from app.services.permissions import Permission
from app.services.user_admin_service import UserAdminService
from app.services.username import normalize_username


class BlogService:
    def __init__(self, users: UserRepository, user_admin: UserAdminService) -> None:
        self._users = users
        self._user_admin = user_admin

    def get_public_owner(self, username: str) -> User:
        """El dueño del blog, si es visible: existe, no esta deshabilitado y
        tiene el permiso `blog`. Cualquier otro caso es el mismo
        BlogNotFoundError (404), para no revelar que usernames existen."""
        user = self._users.get_by_username(normalize_username(username))
        if (
            user is None
            or user.disabled_at is not None
            or Permission.BLOG not in self._user_admin.effective_permissions(user)
        ):
            raise BlogNotFoundError("Blog no encontrado")
        return user
