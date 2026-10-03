"""Administracion de usuarios por consola, mientras no exista la pantalla de admin.

Uso (desde ulm-core, con el venv activo y la base migrada):
    python -m scripts.manage_users list
    python -m scripts.manage_users invite ana@gmail.com --name "Ana"
    python -m scripts.manage_users set-email 1 ruben@gmail.com
    python -m scripts.manage_users disable ana@gmail.com
    python -m scripts.manage_users enable ana@gmail.com

Invitar crea el usuario sin identidad: entra con el primer login de Google
con ese email. En modo Testing de Google, ese email tambien tiene que estar en
la lista de test users de la consola de Google.

Es una capa fina sobre UserAdminService (mismas reglas que tendra la UI): aca
solo se parsean argumentos y se hace el commit.
"""

import argparse
import sys
from collections.abc import Callable, Sequence

from sqlalchemy.orm import Session

import app.main  # noqa: F401 -- registra todos los modelos en Base.metadata
from app.db.session import SessionLocal
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.repositories.sqlalchemy_user_session_repository import SqlAlchemyUserSessionRepository
from app.services.errors import DomainError
from app.services.user_admin_service import UserAdminService


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m scripts.manage_users")
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="Lista los usuarios")

    invite = commands.add_parser("invite", help="Crea un usuario que entra con Google")
    invite.add_argument("email")
    invite.add_argument("--name", help="Si se omite, se toma de Google en el primer login")

    set_email = commands.add_parser("set-email", help="Cambia el email de un usuario")
    set_email.add_argument("user_id", type=int)
    set_email.add_argument("email")

    for name, help_text in (("disable", "Corta el acceso"), ("enable", "Lo devuelve")):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("email")
    return parser


def _describe(service: UserAdminService, user) -> str:
    if user.disabled_at is not None:
        state = "deshabilitado"
    elif service.has_logged_in(user.id):
        state = "activo"
    else:
        state = "invitado (sin login todavia)"
    return f"{user.id:>4}  {user.email:<40} {user.name:<25} {user.timezone:<20} {state}"


def main(
    argv: Sequence[str] | None = None,
    session_factory: Callable[[], Session] = SessionLocal,
) -> int:
    args = _parser().parse_args(argv)
    db = session_factory()
    service = UserAdminService(SqlAlchemyUserRepository(db), SqlAlchemyUserSessionRepository(db))
    try:
        if args.command == "list":
            for user in service.list_users():
                print(_describe(service, user))
            return 0
        if args.command == "invite":
            user = service.invite(args.email, name=args.name)
        elif args.command == "set-email":
            user = service.set_email(args.user_id, args.email)
        elif args.command == "disable":
            user = service.disable(service.get_by_email(args.email).id)
        else:
            user = service.enable(service.get_by_email(args.email).id)
        db.commit()
        print(_describe(service, user))
        return 0
    except DomainError as exc:
        db.rollback()
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
