"""Autorizacion por modulos: permisos de dominio y admin por configuracion.

Usan `real_permissions`: sin el reemplazo de conftest, el usuario por defecto
(id 1, ruben@example.com) arranca sin ningun permiso.
"""

import pytest
from fastapi.routing import APIRoute

from app.api.deps import get_current_user
from app.core.config import settings
from app.db.models.user import UserPermission
from app.main import PUBLIC_ROUTERS, app
from app.repositories.sqlalchemy_user_permission_repository import (
    SqlAlchemyUserPermissionRepository,
)
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.repositories.sqlalchemy_user_session_repository import SqlAlchemyUserSessionRepository
from app.services.errors import (
    AdminRoleNotEditableError,
    MissingBasePermissionError,
    UnknownPermissionError,
)
from app.services.permissions import ALL_PERMISSIONS, Permission
from app.services.user_admin_service import UserAdminService
from tests.conftest import client

API = "/api/v1"

pytestmark = pytest.mark.usefixtures("real_permissions")

# Un GET representativo de cada router, con el permiso que deberia exigir.
DOMAIN_ENDPOINTS = [
    ("/weights/", Permission.WEIGHT),
    ("/meals/", Permission.MEALS),
    ("/expenses/", Permission.FINANCES),
    ("/incomes/direct", Permission.FINANCES),
    ("/checklists/categories", Permission.PLANNING),
    ("/calendar-tasks?date=2026-10-01", Permission.PLANNING),
    ("/calendar-events?first_day=2026-10-01&last_day=2026-10-07", Permission.PLANNING),
]


@pytest.fixture
def service(db_session) -> UserAdminService:
    return UserAdminService(
        SqlAlchemyUserRepository(db_session),
        SqlAlchemyUserSessionRepository(db_session),
        SqlAlchemyUserPermissionRepository(db_session),
    )


def _grant(db_session, *permissions: str, user_id: int = 1) -> None:
    db_session.add_all(UserPermission(user_id=user_id, permission=p) for p in permissions)
    db_session.commit()


# --- Rutas ---


@pytest.mark.parametrize(("path", "permission"), DOMAIN_ENDPOINTS)
def test_domain_routes_require_their_permission(db_session, path, permission):
    assert client.get(f"{API}{path}").status_code == 403

    _grant(db_session, permission.value)

    assert client.get(f"{API}{path}").status_code == 200


def test_a_permission_only_opens_its_own_domain(db_session):
    _grant(db_session, Permission.WEIGHT.value)

    assert client.get(f"{API}/weights/").status_code == 200
    assert client.get(f"{API}/expenses/").status_code == 403
    assert client.get(f"{API}/checklists/categories").status_code == 403


def test_the_ai_permission_alone_does_not_open_the_base_domain(db_session):
    # Solo se llega a este estado escribiendo directo en la base (el service
    # exige el base), pero la ruta igual tiene que pedir el base.
    _grant(db_session, Permission.FINANCES_AI.value)

    assert client.get(f"{API}/expenses/").status_code == 403


def test_writes_are_also_protected(db_session):
    response = client.post(f"{API}/weights/", json={"weight_kg": 70, "recorded_on": "2026-10-01"})

    assert response.status_code == 403


def test_me_needs_only_a_session():
    body = client.get(f"{API}/me").json()

    assert body["permissions"] == []
    assert body["is_admin"] is False


def test_me_lists_the_effective_permissions(db_session):
    _grant(db_session, "planning", "finances", "un.permiso.viejo")

    assert client.get(f"{API}/me").json()["permissions"] == ["finances", "planning"]


# --- Admin por configuracion ---


def test_admin_from_config_has_every_permission(monkeypatch):
    # Normalizado igual que users.email: mayusculas y espacios no importan.
    monkeypatch.setattr(settings, "admin_emails", " otro@gmail.com ,  RUBEN@Example.com ")

    body = client.get(f"{API}/me").json()

    assert body["is_admin"] is True
    assert body["permissions"] == sorted(p.value for p in ALL_PERMISSIONS)
    for path, _ in DOMAIN_ENDPOINTS:
        assert client.get(f"{API}{path}").status_code == 200, path


def test_without_admin_emails_nobody_is_admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "")

    assert client.get(f"{API}/me").json()["is_admin"] is False


# --- Asignacion (UserAdminService) ---


def test_grant_and_revoke(service):
    assert service.grant(1, "finances", granted_by=None) == {Permission.FINANCES}
    # Idempotente.
    assert service.grant(1, "finances", granted_by=None) == {Permission.FINANCES}
    assert service.revoke(1, "finances") == frozenset()


def test_grant_rejects_an_unknown_permission(service):
    with pytest.raises(UnknownPermissionError):
        service.grant(1, "platform.admin", granted_by=None)


def test_ai_permission_requires_its_base(service):
    with pytest.raises(MissingBasePermissionError):
        service.grant(1, "finances.ai", granted_by=None)

    service.grant(1, "finances", granted_by=None)

    assert service.grant(1, "finances.ai", granted_by=None) == {
        Permission.FINANCES,
        Permission.FINANCES_AI,
    }


def test_revoking_the_base_also_revokes_its_ai(service):
    service.grant(1, "finances", granted_by=None)
    service.grant(1, "finances.ai", granted_by=None)
    service.grant(1, "planning", granted_by=None)

    assert service.revoke(1, "finances") == {Permission.PLANNING}


def test_grant_records_who_granted_it(service, db_session, other_user):
    service.grant(other_user, "meals", granted_by=1)

    row = db_session.get(UserPermission, (other_user, "meals"))
    assert row.granted_by == 1


def test_the_admin_user_is_not_editable(service, monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "ruben@example.com")

    with pytest.raises(AdminRoleNotEditableError):
        service.grant(1, "finances", granted_by=None)
    with pytest.raises(AdminRoleNotEditableError):
        service.revoke(1, "finances")
    with pytest.raises(AdminRoleNotEditableError):
        service.disable(1)


# --- Fail-closed ---


def _required_permissions(dependant) -> set[Permission]:
    found = set()
    for dep in dependant.dependencies:
        permission = getattr(dep.call, "required_permission", None)
        if permission is not None:
            found.add(permission)
        found |= _required_permissions(dep)
    return found


def _private_routes() -> list[APIRoute]:
    public_paths = {
        f"{settings.api_prefix}{route.path}" for router in PUBLIC_ROUTERS for route in router.routes
    }
    return [
        route
        for route in app.routes
        if isinstance(route, APIRoute) and route.path not in public_paths and route.path != "/"
    ]


def test_every_private_route_except_me_requires_a_permission():
    """Si alguien monta un router nuevo con permiso None, o una ruta suelta,
    esto falla: un modulo no queda abierto a cualquier usuario logueado."""
    missing = [
        route.path
        for route in _private_routes()
        if route.path != f"{API}/me" and not _required_permissions(route.dependant)
    ]

    assert missing == []


@pytest.mark.parametrize(
    ("prefix", "permission"),
    [
        ("/weights", Permission.WEIGHT),
        ("/meals", Permission.MEALS),
        ("/expenses", Permission.FINANCES),
        ("/incomes", Permission.FINANCES),
        ("/checklists", Permission.PLANNING),
        ("/calendar-tasks", Permission.PLANNING),
        ("/calendar-events", Permission.PLANNING),
    ],
)
def test_each_router_requires_the_right_permission(prefix, permission):
    """Atrapa un permiso mal asignado en PRIVATE_ROUTERS (ej. incomes -> meals)."""
    routes = [r for r in _private_routes() if r.path.startswith(f"{API}{prefix}")]

    assert routes
    for route in routes:
        assert _required_permissions(route.dependant) == {permission}, route.path
        assert any(dep.call is get_current_user for dep in route.dependant.dependencies)
