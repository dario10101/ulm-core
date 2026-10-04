"""Administracion de usuarios (/admin/users, solo admin): listar, invitar,
asignar permisos y deshabilitar.

El usuario por defecto (id 1, ruben@example.com) es el admin en estos tests;
`other_user` (id 2) es al que se administra.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import settings
from app.db.models.user import UserIdentity, UserPermission, UserSession
from app.services.auth_service import hash_token
from tests.conftest import client

API = "/api/v1/admin/users"

pytestmark = pytest.mark.usefixtures("real_permissions")


@pytest.fixture(autouse=True)
def as_admin(monkeypatch):
    monkeypatch.setattr(settings, "admin_emails", "ruben@example.com")


def _user(email: str) -> dict:
    return next(u for u in client.get(API).json() if u["email"] == email)


# --- Acceso ---


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("get", "", None),
        ("post", "", {"email": "nueva@gmail.com"}),
        ("put", "/2/permissions", {"permissions": ["finances"]}),
        ("post", "/2/disable", None),
        ("post", "/2/enable", None),
    ],
)
def test_non_admin_gets_403(monkeypatch, db_session, other_user, method, path, body):
    monkeypatch.setattr(settings, "admin_emails", "otra@example.com")
    # Ni con todos los permisos de dominio: administrar usuarios no es uno.
    db_session.add_all(
        UserPermission(user_id=1, permission=p) for p in ("finances", "planning", "weight")
    )
    db_session.commit()

    kwargs = {"json": body} if body is not None else {}
    assert getattr(client, method)(f"{API}{path}", **kwargs).status_code == 403
    assert db_session.get(UserPermission, (other_user, "finances")) is None


# --- Listar ---


def test_list_shows_status_and_permissions(db_session, other_user):
    db_session.add(UserPermission(user_id=other_user, permission="meals"))
    db_session.commit()

    users = {u["email"]: u for u in client.get(API).json()}

    admin = users["ruben@example.com"]
    assert admin["is_admin"] is True
    assert "finances.ai" in admin["permissions"]
    other = users["otra@example.com"]
    assert other["is_admin"] is False
    assert other["status"] == "invited"
    assert other["permissions"] == ["meals"]


def test_status_follows_login_and_disable(db_session, other_user):
    db_session.add(
        UserIdentity(
            user_id=other_user,
            provider="google",
            provider_subject="sub-2",
            email_at_link="otra@example.com",
        )
    )
    db_session.commit()
    assert _user("otra@example.com")["status"] == "active"

    client.post(f"{API}/{other_user}/disable")
    assert _user("otra@example.com")["status"] == "disabled"


# --- Invitar ---


def test_invite_creates_an_invited_user_without_permissions():
    response = client.post(API, json={"email": "  Nueva@Gmail.com ", "name": "  "})

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "nueva@gmail.com"
    assert body["name"] == "nueva"
    assert body["status"] == "invited"
    assert body["permissions"] == []


def test_invite_rejects_a_taken_email(other_user):
    assert client.post(API, json={"email": "OTRA@example.com"}).status_code == 409


@pytest.mark.parametrize("email", ["", "sin-arroba", "a@b", "con espacio@x.com"])
def test_invite_rejects_an_invalid_email(email):
    assert client.post(API, json={"email": email}).status_code == 422


# --- Permisos ---


def _put(user_id: int, *permissions: str):
    return client.put(f"{API}/{user_id}/permissions", json={"permissions": list(permissions)})


def test_put_replaces_the_whole_set(other_user):
    assert _put(other_user, "finances", "finances.ai", "planning").json()["permissions"] == [
        "finances",
        "finances.ai",
        "planning",
    ]

    assert _put(other_user, "planning").json()["permissions"] == ["planning"]
    assert _put(other_user).json()["permissions"] == []


def test_put_keeps_who_granted_what_did_not_change(db_session, other_user):
    old = datetime(2026, 1, 1, tzinfo=UTC)
    db_session.add(
        UserPermission(user_id=other_user, permission="meals", granted_by=None, granted_at=old)
    )
    db_session.commit()

    _put(other_user, "meals", "weight")

    db_session.expire_all()
    kept = db_session.get(UserPermission, (other_user, "meals"))
    assert kept.granted_by is None
    assert kept.granted_at.replace(tzinfo=UTC) == old
    assert db_session.get(UserPermission, (other_user, "weight")).granted_by == 1


def test_put_cleans_values_no_longer_in_the_catalog(db_session, other_user):
    db_session.add(UserPermission(user_id=other_user, permission="habits"))
    db_session.commit()

    _put(other_user, "meals")

    assert db_session.get(UserPermission, (other_user, "habits")) is None


def test_put_rejects_an_ai_permission_without_its_base(db_session, other_user):
    _put(other_user, "meals")

    response = _put(other_user, "finances.ai", "meals")

    assert response.status_code == 422
    assert "finances" in response.json()["detail"]
    # Nada a medias: sigue como estaba.
    assert _user("otra@example.com")["permissions"] == ["meals"]


def test_put_rejects_an_unknown_permission(other_user):
    assert _put(other_user, "platform.admin").status_code == 422


def test_put_on_a_missing_user_is_404():
    assert _put(999, "meals").status_code == 404


def test_permission_changes_apply_on_the_next_request(other_user):
    from tests.conftest import acting_as

    _put(other_user, "weight")
    with acting_as(other_user):
        assert client.get("/api/v1/weights/").status_code == 200

    _put(other_user)
    with acting_as(other_user):
        assert client.get("/api/v1/weights/").status_code == 403


# --- Deshabilitar ---


def test_disable_closes_the_sessions_and_enable_lets_back_in(db_session, other_user):
    db_session.add(
        UserSession(
            user_id=other_user,
            token_hash=hash_token("token-de-otra"),
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db_session.commit()

    assert client.post(f"{API}/{other_user}/disable").json()["status"] == "disabled"
    db_session.expire_all()
    assert db_session.query(UserSession).filter_by(user_id=other_user).count() == 0

    assert client.post(f"{API}/{other_user}/enable").json()["status"] == "invited"


# --- El admin no se edita ---


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("put", "/1/permissions", {"permissions": []}),
        ("post", "/1/disable", None),
    ],
)
def test_the_admin_is_not_editable(db_session, method, path, body):
    kwargs = {"json": body} if body is not None else {}

    assert getattr(client, method)(f"{API}{path}", **kwargs).status_code == 409
    db_session.expire_all()
    assert _user("ruben@example.com")["status"] != "disabled"
