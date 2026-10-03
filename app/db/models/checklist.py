"""Modelos ORM del modulo de checklists: categorias, template semanal, y las
semanas/tareas concretas generadas a partir de ese template."""

from datetime import UTC, date, datetime

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class ChecklistCategory(Base):
    __tablename__ = "cl_user_categories"
    __table_args__ = (
        Index("ix_cl_user_categories_user_priority", "user_id", "priority"),
        # Un nombre por usuario, sin distinguir mayusculas y contando tambien
        # las DISABLED: dos categorias "Salud" con datos historicos saldrian
        # por separado en analytics. Es un indice y no una UNIQUE constraint
        # porque en Postgres una constraint no admite expresiones (lower()).
        Index(
            "uq_cl_user_categories_user_id_name", "user_id", func.lower(text("name")), unique=True
        ),
        # Redundante como unicidad (id ya es PK), pero es lo que permite que
        # las tablas hijas declaren FOREIGN KEY (user_id, category_id): asi
        # Postgres rechaza una fila que apunte a la categoria de otro usuario,
        # aunque el service tenga un bug. Ver category_owner_fk.
        UniqueConstraint("user_id", "id", name="uq_cl_user_categories_user_id_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, nullable=False)
    # ENABLED o DISABLED (ver app.schemas.checklist.CategoryStatus). Eliminar una
    # categoria es un soft-delete: nunca se borra la fila, para no perder la
    # referencia historica desde cl_week_tasks/cl_week_category_day_score.
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ENABLED", server_default="ENABLED"
    )


def category_owner_fk() -> ForeignKeyConstraint:
    """FK compuesta (user_id, category_id) -> cl_user_categories(user_id, id).

    Reemplaza a la FK simple sobre category_id: ademas de exigir que la
    categoria exista, exige que sea del mismo usuario que la fila. Es una
    funcion y no una constante porque cada tabla necesita su propia instancia."""
    return ForeignKeyConstraint(
        ["user_id", "category_id"], ["cl_user_categories.user_id", "cl_user_categories.id"]
    )


def week_owner_fk() -> ForeignKeyConstraint:
    """FK compuesta (user_id, cl_week_id) -> cl_user_weeks(user_id, id): el
    user_id desnormalizado de una fila hija no puede contradecir al de su
    semana."""
    return ForeignKeyConstraint(
        ["user_id", "cl_week_id"], ["cl_user_weeks.user_id", "cl_user_weeks.id"]
    )


class ChecklistTemplateTask(Base):
    __tablename__ = "cl_user_template_tasks"
    __table_args__ = (category_owner_fk(),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # Dueño explicito. Antes se derivaba por join con la categoria, lo que
    # costaba un query extra en cada chequeo y dejaba el aislamiento entre
    # usuarios dependiendo de que la categoria estuviera bien asignada.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Dias 1-7 separados por coma (ej. "1,2,4,5") cuando la tarea aplica a varios dias
    day_of_week: Mapped[str] = mapped_column(String(20), nullable=False)
    # HIGH (2 puntos) o STANDARD (1 punto), ver app.schemas.checklist.Importance
    importance: Mapped[str] = mapped_column(String(20), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class ChecklistWeek(Base):
    """Resumen de una semana de checklist: rango de fechas elegido y si ya se cerro."""

    __tablename__ = "cl_user_weeks"
    __table_args__ = (
        # A lo sumo una semana abierta por usuario. WeekService ya lo valida,
        # esto cubre dos requests concurrentes que pasen ambas la validacion.
        # Indice unico *parcial*: solo indexa las filas que cumplen el WHERE.
        Index(
            "uq_cl_user_weeks_user_id_open",
            "user_id",
            unique=True,
            postgresql_where=text("NOT closed"),
            sqlite_where=text("NOT closed"),
        ),
        # Destino de las FK compuestas de cl_week_tasks y
        # cl_week_category_day_score (ver week_owner_fk).
        UniqueConstraint("user_id", "id", name="uq_cl_user_weeks_user_id_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    first_day: Mapped[date] = mapped_column(Date, nullable=False)
    last_day: Mapped[date] = mapped_column(Date, nullable=False)
    closed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    closed_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Se calcula una unica vez, al cerrar la semana (ver ChecklistTaskService.close_week)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ChecklistTask(Base):
    """Tarea concreta de una semana, copiada desde cl_user_template_tasks al crear la semana."""

    __tablename__ = "cl_week_tasks"
    __table_args__ = (week_owner_fk(), category_owner_fk())

    id: Mapped[int] = mapped_column(primary_key=True)
    # Dueño desnormalizado (tambien lo tiene la semana): cada query filtra por
    # esta columna sin join, y las FK compuestas garantizan que coincida con
    # el de la semana y el de la categoria. No lleva FK propia a users: la de
    # la semana ya la cubre.
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Indexada a mano: Postgres no indexa las FK solo, y esta tabla (la que
    # mas crece) siempre se consulta por semana.
    cl_week_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # A diferencia de cl_user_template_tasks, aca siempre es un unico dia 1-7 (sin CSV):
    # una tarea de template que aplica a varios dias genera una fila por dia.
    day_of_week: Mapped[str] = mapped_column(String(2), nullable=False)
    importance: Mapped[str] = mapped_column(String(20), nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDING")
    last_modified_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )


class ChecklistWeekCategoryDayScore(Base):
    """Puntaje ya agregado por (semana, categoria, dia), calculado una unica
    vez al cerrar la semana (ver WeekService.close_week). Semana cerrada es
    inmutable, asi que esto se computa una sola vez y nunca se recalcula.

    Es el grano mas fino que vale la pena materializar: cualquier rollup mas
    grueso (total semanal por categoria, mensual, por dia de la semana, etc.)
    sale de un SUM/GROUP BY sobre un puñado de filas por semana, sin volver a
    tocar cl_week_tasks (que crece sin limite con los anios)."""

    __tablename__ = "cl_week_category_day_score"
    __table_args__ = (
        UniqueConstraint(
            "cl_week_id", "category_id", "day_of_week", name="uq_wcds_week_category_day"
        ),
        Index("ix_wcds_week", "cl_week_id"),
        Index("ix_wcds_category", "category_id"),
        week_owner_fk(),
        category_owner_fk(),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Mismo criterio que ChecklistTask.user_id.
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    cl_week_id: Mapped[int] = mapped_column(Integer, nullable=False)
    category_id: Mapped[int] = mapped_column(Integer, nullable=False)
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Suma de puntos posibles de todas las tareas de esa combinacion, sin
    # filtrar por status (habilita "% de cumplimiento" a futuro sin volver a
    # tocar cl_week_tasks).
    points_possible: Mapped[int] = mapped_column(Integer, nullable=False)
