"""Administracion de usuarios (Settings -> Users): invitar, asignar permisos,
deshabilitar. Solo el admin (ver PRIVATE_ROUTERS en app/main.py). Mismo
UserAdminService que scripts/manage_users.py, asi las reglas son las mismas."""

from fastapi import APIRouter, Depends

from app.api.deps import get_current_user_id, get_user_admin_service
from app.api.errors import http_error
from app.db.models.user import User
from app.schemas.user import UserAdminRead, UserInvite, UserPermissionsWrite
from app.services.errors import DomainError
from app.services.user_admin_service import UserAdminService

router = APIRouter(prefix="/admin/users", tags=["admin users"])


def _read(service: UserAdminService, user: User) -> UserAdminRead:
    return UserAdminRead(
        id=user.id,
        name=user.name,
        email=user.email,
        avatar_url=user.avatar_url,
        status=service.status(user),
        is_admin=service.is_admin(user),
        permissions=sorted(p.value for p in service.effective_permissions(user)),
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("", response_model=list[UserAdminRead])
def list_users(service: UserAdminService = Depends(get_user_admin_service)) -> list[UserAdminRead]:
    # Dos queries por usuario (identidad y permisos): con 5-10 usuarios no
    # justifica una consulta agregada.
    return [_read(service, user) for user in service.list_users()]


@router.post("", response_model=UserAdminRead, status_code=201)
def invite_user(
    payload: UserInvite, service: UserAdminService = Depends(get_user_admin_service)
) -> UserAdminRead:
    try:
        return _read(service, service.invite(payload.email, name=payload.name))
    except DomainError as exc:
        raise http_error(exc)


@router.put("/{user_id}/permissions", response_model=UserAdminRead)
def set_user_permissions(
    user_id: int,
    payload: UserPermissionsWrite,
    admin_id: int = Depends(get_current_user_id),
    service: UserAdminService = Depends(get_user_admin_service),
) -> UserAdminRead:
    try:
        service.set_permissions(user_id, payload.permissions, granted_by=admin_id)
        return _read(service, service.get(user_id))
    except DomainError as exc:
        raise http_error(exc)


@router.post("/{user_id}/disable", response_model=UserAdminRead)
def disable_user(
    user_id: int, service: UserAdminService = Depends(get_user_admin_service)
) -> UserAdminRead:
    try:
        return _read(service, service.disable(user_id))
    except DomainError as exc:
        raise http_error(exc)


@router.post("/{user_id}/enable", response_model=UserAdminRead)
def enable_user(
    user_id: int, service: UserAdminService = Depends(get_user_admin_service)
) -> UserAdminRead:
    try:
        return _read(service, service.enable(user_id))
    except DomainError as exc:
        raise http_error(exc)
