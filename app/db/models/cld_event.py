"""Modelo ORM de eventos generales de calendario (cld_events): festivos y
otros eventos con rango de fechas, no ligados a un usuario en particular."""

from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class CldEvent(Base):
    __tablename__ = "cld_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    # Ej. "HOLIDAY" para festivos; deja lugar a otros tipos de evento general.
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    first_day: Mapped[date] = mapped_column(Date, nullable=False)
    last_day: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
