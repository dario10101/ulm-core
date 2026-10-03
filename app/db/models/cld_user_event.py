"""Modelo ORM de eventos personales del usuario (cld_user_events): rangos de
fechas propios (ej. vacaciones, viajes), sin CRUD en el front todavia."""

from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base
from app.db.models.checklist import category_owner_fk


class CldUserEvent(Base):
    __tablename__ = "cld_user_events"
    # La categoria tiene que ser del mismo usuario (ver category_owner_fk).
    __table_args__ = (category_owner_fk(),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Ej. "TRAVEL", "VACATION", "BIRTHDAY"; mismo proposito que CldEvent.code.
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    first_day: Mapped[date] = mapped_column(Date, nullable=False)
    last_day: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
