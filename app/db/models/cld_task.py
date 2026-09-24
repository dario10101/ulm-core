"""Modelo ORM de tareas de calendario (cld_tasks): tareas puntuales o
recurrentes, con sincronizacion opcional hacia el checklist semanal."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class CldTask(Base):
    __tablename__ = "cld_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("cl_categories.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    importance: Mapped[str] = mapped_column(String(20), nullable=False)
    notify: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Fecha/hora puntual de la tarea. Nulo si la tarea es recurrente (ver repeat_mode).
    scheduled_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Duracion en minutos desde la hora de inicio (scheduled_date/repeat_date).
    # Nunca cruza la medianoche del dia de inicio (se valida en el schema).
    duration_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=60, server_default="60"
    )
    # WEEKLY, MONTHLY, YEARLY, o None si la tarea no se repite
    repeat_mode: Mapped[str | None] = mapped_column(String(10), nullable=True)
    # Fecha/hora ancla de la recurrencia: se usa su dia de semana (WEEKLY), su
    # dia del mes con clamp al ultimo dia disponible (MONTHLY), o su dia+mes
    # (YEARLY); la hora siempre se respeta. Nulo si la tarea no se repite.
    repeat_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Si True, cada ocurrencia de esta tarea que caiga dentro del rango de una
    # semana (actual o futura) se agrega a cl_tasks. El template nunca se toca.
    add_to_checklist: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Fechas ISO separadas por coma (ej. "2026-09-23,2026-10-07"): ocurrencias
    # puntuales de una serie recurrente que el usuario borro solo para ese dia
    # (ver CldTaskService.delete_task). No aplica a tareas que no repiten.
    excluded_dates: Mapped[str | None] = mapped_column(Text, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
