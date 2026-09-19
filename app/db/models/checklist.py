"""Modelos ORM del modulo de checklists: categorias, template semanal, y las
semanas/tareas concretas generadas a partir de ese template."""

from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ChecklistCategory(Base):
    __tablename__ = "cl_categories"
    __table_args__ = (Index("ix_cl_categories_user_priority", "user_id", "priority"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)


class ChecklistTemplateTask(Base):
    __tablename__ = "cl_template_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Dias 1-7 separados por coma (ej. "1,2,4,5") cuando la tarea aplica a varios dias
    day_of_week: Mapped[str] = mapped_column(String(20), nullable=False)
    # HIGH (2 puntos) o STANDARD (1 punto), ver app.schemas.checklist.Importance
    importance: Mapped[str] = mapped_column(String(20), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("cl_categories.id"), nullable=False)


class ChecklistWeek(Base):
    """Resumen de una semana de checklist: rango de fechas elegido y si ya se cerro."""

    __tablename__ = "cl_week"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    first_day: Mapped[date] = mapped_column(Date, nullable=False)
    last_day: Mapped[date] = mapped_column(Date, nullable=False)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    closed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Se calcula una unica vez, al cerrar la semana (ver ChecklistTaskService.close_week)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ChecklistTask(Base):
    """Tarea concreta de una semana, copiada desde cl_template_tasks al crear la semana."""

    __tablename__ = "cl_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    cl_week_id: Mapped[int] = mapped_column(ForeignKey("cl_week.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # A diferencia de cl_template_tasks, aca siempre es un unico dia 1-7 (sin CSV):
    # una tarea de template que aplica a varios dias genera una fila por dia.
    day_of_week: Mapped[str] = mapped_column(String(2), nullable=False)
    importance: Mapped[str] = mapped_column(String(20), nullable=False)
    category_id: Mapped[int] = mapped_column(ForeignKey("cl_categories.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    last_modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
