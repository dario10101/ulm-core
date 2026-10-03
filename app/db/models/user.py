"""Modelos ORM de usuarios y autenticacion.

Un usuario (`users`) es la persona y dueña de los datos. Como entra lo dicen
sus identidades (`user_identities`): hoy solo Google, a futuro tambien
contraseña, sin tocar `users`. Un usuario sin identidades es una invitacion
pendiente: el primer login con Google con ese email la vincula.
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


def _now() -> datetime:
    return datetime.now(UTC)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Un email por usuario sin distinguir mayusculas: la invitacion y el
        # login buscan por email, y "Ana@x.com" y "ana@x.com" son la misma
        # persona. Indice y no constraint por la expresion (mismo caso que
        # uq_cl_user_categories_user_id_name).
        Index("uq_users_email", func.lower(text("email")), unique=True),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Se guarda ya normalizado (minusculas, sin espacios), ver normalize_email.
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Zona horaria IANA (ej. "America/Bogota"). Toda cuenta de calendario
    # (dia, dia de semana, dia del mes) se hace convirtiendo a esta zona
    # primero; la BD guarda siempre UTC. Ver app/services/cld_task_sync.py.
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/Bogota", server_default="America/Bogota"
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Deshabilitar en vez de borrar: corta el acceso y conserva los datos.
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class UserIdentity(Base):
    """Una forma de entrar de un usuario: (proveedor, id estable en ese proveedor)."""

    __tablename__ = "user_identities"
    __table_args__ = (
        UniqueConstraint(
            "provider", "provider_subject", name="uq_user_identities_provider_subject"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # "google" por ahora; "password" cuando exista.
    provider: Mapped[str] = mapped_column(String(20), nullable=False)
    # El `sub` del id_token de Google: estable aunque el usuario cambie su
    # email. Por eso el login busca por esto y no por email.
    provider_subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # Email que tenia la cuenta al vincularla (auditoria; no se usa para buscar).
    email_at_link: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class UserSession(Base):
    """Sesion de login. La cookie lleva un token aleatorio; aca solo se guarda
    su SHA-256, asi que leer esta tabla no alcanza para hacerse pasar por nadie
    (mismo principio que no guardar contraseñas en claro)."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    # Expiracion deslizante: se corre hacia adelante con el uso (ver AuthService).
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)
