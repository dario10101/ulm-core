"""Datos del usuario logueado."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_permissions, get_current_user
from app.db.models.user import User
from app.schemas.user import MeRead
from app.services.permissions import Permission, is_admin_email

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeRead)
def read_me(
    user: User = Depends(get_current_user),
    permissions: frozenset[Permission] = Depends(get_current_permissions),
) -> MeRead:
    return MeRead(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        timezone=user.timezone,
        is_admin=is_admin_email(user.email),
        permissions=sorted(permission.value for permission in permissions),
    )
