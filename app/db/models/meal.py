"""Modelo ORM de registros de comida (meals)."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class Meal(Base):
    __tablename__ = "meals"
    __table_args__ = (Index("ix_meals_user_recorded_on", "user_id", "recorded_on"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Fecha y hora a la que corresponde la comida: hora de pared del usuario,
    # convertida a UTC por el service antes de guardar (ver
    # app/services/cld_task_sync.to_utc, mismo contrato que cld_tasks).
    recorded_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # DESAYUNO/MEDIA_MANANA/ALMUERZO/MEDIA_TARDE/CENA/EXTRA_NOCTURNO (ver MealType).
    meal_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # Porcentaje de una porcion completa que representa el plato (0-100).
    meal_size: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    # Deliberadamente no normalizado a una tabla aparte: texto plano
    # "NOMBRE:PORCENTAJE;NOMBRE:PORCENTAJE", en mayusculas, sin tildes ni
    # caracteres especiales y ordenado alfabeticamente (ver
    # app/services/meal_content.py, que arma este string).
    meal_content: Mapped[str | None] = mapped_column(String(500), nullable=True)
    drink: Mapped[str | None] = mapped_column(String(60), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
