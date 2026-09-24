"""Modelo ORM de usuarios. Sin auth todavia: existe para que las tablas de
registros (weights, etc.) tengan a quien referenciar via foreign key."""

from datetime import datetime, timezone

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    # Zona horaria IANA (ej. "America/Bogota"). Toda cuenta de calendario
    # (dia, dia de semana, dia del mes) se hace convirtiendo a esta zona
    # primero; la BD guarda siempre UTC. Ver app/services/cld_task_sync.py.
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="America/Bogota", server_default="America/Bogota"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
