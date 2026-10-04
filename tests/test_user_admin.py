"""Administracion de usuarios: el service y el script que lo expone por consola."""

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.user import User, UserSession
from app.repositories.sqlalchemy_user_permission_repository import (
    SqlAlchemyUserPermissionRepository,
)
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.repositories.sqlalchemy_user_session_repository import SqlAlchemyUserSessionRepository
from app.services.errors import EmailTakenError, UserNotFoundError
from app.services.user_admin_service import UserAdminService
from scripts import manage_users


@pytest.fixture
def service(db_session) -> UserAdminService:
    return UserAdminService(
        SqlAlchemyUserRepository(db_session),
        SqlAlchemyUserSessionRepository(db_session),
        SqlAlchemyUserPermissionRepository(db_session),
    )


def test_invite_normalizes_the_email_and_defaults_the_name(service):
    user = service.invite("  Ana.Perez@Gmail.COM ")

    assert user.email == "ana.perez@gmail.com"
    assert user.name == "ana.perez"
    assert user.timezone == "America/Bogota"
    assert not service.has_logged_in(user.id)


@pytest.mark.parametrize("email", ["ruben@example.com", "RUBEN@example.com"])
def test_invite_rejects_an_email_already_taken(service, email):
    with pytest.raises(EmailTakenError):
        service.invite(email)


def test_set_email_rejects_another_users_email(service):
    other = service.invite("ana@gmail.com")

    with pytest.raises(EmailTakenError):
        service.set_email(other.id, "Ruben@Example.com")
    # Reasignarse el propio email (en otro formato) no es un conflicto.
    assert service.set_email(1, "RUBEN@example.com").email == "ruben@example.com"


def test_disable_closes_the_users_sessions(service, db_session):
    now = datetime.now(UTC)
    db_session.add(UserSession(user_id=1, token_hash="h" * 64, expires_at=now + timedelta(days=1)))
    db_session.commit()

    user = service.disable(1)

    assert user.disabled_at is not None
    assert db_session.query(UserSession).count() == 0
    assert service.enable(1).disabled_at is None


def test_unknown_user_raises(service):
    with pytest.raises(UserNotFoundError):
        service.get_by_email("nadie@gmail.com")
    with pytest.raises(UserNotFoundError):
        service.set_email(999, "x@gmail.com")


# --- Script ---


def _run(db_session, *argv: str) -> int:
    # El script cierra su sesion al terminar; se le da una vista que no cierre
    # la del test (que la fixture revierte al final).
    class _Borrowed:
        def __getattr__(self, name):
            return getattr(db_session, name)

        def close(self):
            pass

    return manage_users.main(list(argv), session_factory=_Borrowed)


def test_script_invites_and_lists(db_session, capsys):
    assert _run(db_session, "invite", "ana@gmail.com", "--name", "Ana") == 0
    assert _run(db_session, "list") == 0

    output = capsys.readouterr().out
    assert "ana@gmail.com" in output
    assert "invitado" in output
    assert db_session.query(User).filter_by(email="ana@gmail.com").one().name == "Ana"


def test_script_sets_email_and_reports_errors(db_session, capsys):
    assert _run(db_session, "set-email", "1", "Ruben.D21PC@gmail.com") == 0
    assert db_session.get(User, 1).email == "ruben.d21pc@gmail.com"

    assert _run(db_session, "invite", "ruben.d21pc@gmail.com") == 1
    assert "Ya existe" in capsys.readouterr().err


def test_script_disables_and_enables(db_session):
    assert _run(db_session, "disable", "ruben@example.com") == 0
    assert db_session.get(User, 1).disabled_at is not None
    assert _run(db_session, "enable", "ruben@example.com") == 0
    assert db_session.get(User, 1).disabled_at is None


def test_script_grants_and_revokes_permissions(db_session, capsys):
    assert _run(db_session, "grant", "ruben@example.com", "finances") == 0
    assert _run(db_session, "grant", "ruben@example.com", "finances.ai") == 0
    assert _run(db_session, "list") == 0
    assert "finances, finances.ai" in capsys.readouterr().out

    assert _run(db_session, "revoke", "ruben@example.com", "finances") == 0
    assert _run(db_session, "list") == 0
    assert "(sin permisos)" in capsys.readouterr().out


def test_script_rejects_invalid_grants(db_session, capsys):
    assert _run(db_session, "grant", "ruben@example.com", "platform.admin") == 1
    assert _run(db_session, "grant", "ruben@example.com", "finances.ai") == 1
    errors = capsys.readouterr().err
    assert "desconocido" in errors
    assert "exige" in errors


def test_script_shows_and_protects_the_config_admin(db_session, capsys, monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "admin_emails", "ruben@example.com")

    assert _run(db_session, "list") == 0
    assert "admin (config)" in capsys.readouterr().out
    assert _run(db_session, "disable", "ruben@example.com") == 1
    assert "ADMIN_EMAILS" in capsys.readouterr().err
