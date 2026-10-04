"""Datos del usuario logueado."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_permissions, get_current_user, get_user_admin_service
from app.api.errors import http_error
from app.db.models.user import User
from app.schemas.user import MeRead, UsernameWrite
from app.services.errors import DomainError
from app.services.permissions import Permission, is_admin_email
from app.services.user_admin_service import UserAdminService

router = APIRouter(prefix="/me", tags=["me"])


def _me(user: User, permissions: frozenset[Permission]) -> MeRead:
    return MeRead(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        timezone=user.timezone,
        username=user.username,
        is_admin=is_admin_email(user.email),
        permissions=sorted(permission.value for permission in permissions),
    )


@router.get("", response_model=MeRead)
def read_me(
    user: User = Depends(get_current_user),
    permissions: frozenset[Permission] = Depends(get_current_permissions),
) -> MeRead:
    return _me(user, permissions)


@router.put("/username", response_model=MeRead)
def set_username(
    payload: UsernameWrite,
    user: User = Depends(get_current_user),
    permissions: frozenset[Permission] = Depends(get_current_permissions),
    user_admin: UserAdminService = Depends(get_user_admin_service),
) -> MeRead:
    """Crea el username (una sola vez). Es de la cuenta, no del blog: no
    exige ningun permiso de dominio, igual que GET /me."""
    try:
        updated = user_admin.set_username(user.id, payload.username)
    except DomainError as exc:
        raise http_error(exc) from exc
    return _me(updated, permissions)
