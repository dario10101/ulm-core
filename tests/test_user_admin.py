"""Administracion de usuarios: el service y el script que lo expone por consola."""

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.finance import (
    Category,
    DefaultExpenseCategory,
    DefaultIncomeSource,
    DefaultIncomeSubcategory,
    DefaultPaymentMethod,
    IncomeSource,
    IncomeSubcategory,
    PaymentMethod,
)
from app.db.models.user import User, UserSession
from app.repositories.sqlalchemy_finance_catalog_repository import (
    SqlAlchemyFinanceCatalogRepository,
)
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
        SqlAlchemyFinanceCatalogRepository(db_session),
    )


def test_invite_normalizes_the_email_and_defaults_the_name(service):
    user = service.invite("  Ana.Perez@Gmail.COM ")

    assert user.email == "ana.perez@gmail.com"
    assert user.name == "ana.perez"
    assert user.timezone == "America/Bogota"
    assert not service.has_logged_in(user.id)


def test_new_user_gets_a_copy_of_the_default_categories(service, db_session):
    db_session.add_all(
        [
            DefaultExpenseCategory(name="Food", icon_key="utensils", color_key="yellow"),
            DefaultExpenseCategory(name="Health", icon_key="heart-pulse", color_key="red"),
        ]
    )
    db_session.flush()

    user = service.invite("ana@example.com")
    # La copia es independiente: cambiar la plantilla despues no la toca.
    db_session.query(DefaultExpenseCategory).delete()
    db_session.flush()

    copies = db_session.query(Category).filter_by(user_id=user.id).order_by(Category.name).all()
    assert [(c.name, c.icon_key, c.color_key, c.status) for c in copies] == [
        ("Food", "utensils", "yellow", "ENABLED"),
        ("Health", "heart-pulse", "red", "ENABLED"),
    ]


def test_new_user_gets_payment_methods_sources_and_subcategories(service, db_session):
    db_session.add(DefaultPaymentMethod(name="Cash", icon_key="banknote", color_key="green"))
    salary = DefaultIncomeSource(name="Salary", type="DIRECT")
    savings = DefaultIncomeSource(name="Savings", type="INTEREST")
    db_session.add_all([salary, savings])
    db_session.flush()
    db_session.add_all(
        [
            DefaultIncomeSubcategory(source_id=salary.id, name="BASE SALARY"),
            DefaultIncomeSubcategory(source_id=salary.id, name="BONUS"),
            DefaultIncomeSubcategory(source_id=savings.id, name="MAIN"),
        ]
    )
    db_session.flush()

    user = service.invite("ana@example.com")

    methods = db_session.query(PaymentMethod).filter_by(user_id=user.id).all()
    assert [(m.name, m.status) for m in methods] == [("Cash", "ENABLED")]
    sources = {s.id: s for s in db_session.query(IncomeSource).filter_by(user_id=user.id)}
    assert sorted((s.name, s.type) for s in sources.values()) == [
        ("Salary", "DIRECT"),
        ("Savings", "INTEREST"),
    ]
    # Cada subcategoria cuelga de la COPIA de su fuente, no de la plantilla.
    subs = db_session.query(IncomeSubcategory).filter_by(user_id=user.id).all()
    assert sorted((sources[s.source_id].name, s.name, s.type) for s in subs) == [
        ("Salary", "BASE SALARY", "DIRECT"),
        ("Salary", "BONUS", "DIRECT"),
        ("Savings", "MAIN", "INTEREST"),
    ]


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
