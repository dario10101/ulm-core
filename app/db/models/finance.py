"""Modelos ORM del modulo de finanzas: catalogos (categorias, metodos de
pago, tags) y registros de gasto.

Categorias y metodos de pago son catalogos globales (no dependen del
usuario); tags son por usuario. Los tres son "soft delete" via `status`
(ENABLED/DISABLED), igual que `ChecklistCategory` (ver app/db/models/checklist.py):
nunca se borra una fila, para no perder la referencia historica desde
fn_user_expenses/fn_expenses_tags.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Category(Base):
    __tablename__ = "fn_categories"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Nombre en kebab-case de un icono de lucide (ej. "shopping-cart"), para
    # que el frontend lo resuelva contra un diccionario fijo sin tener que
    # guardar el componente ni el SVG en la base.
    icon_key: Mapped[str] = mapped_column(String(60), nullable=False)
    # Nombre de un color de una paleta chica y fija que vive solo en el
    # frontend (ver ulm-web/src/config/financeVisuals.ts).
    color_key: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ENABLED", server_default="ENABLED"
    )


class PaymentMethod(Base):
    __tablename__ = "fn_payment_methods"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon_key: Mapped[str] = mapped_column(String(60), nullable=False)
    color_key: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ENABLED", server_default="ENABLED"
    )


class Tag(Base):
    __tablename__ = "fn_user_tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_fn_user_tags_user_id_name"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    color_key: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ENABLED", server_default="ENABLED"
    )


class Expense(Base):
    __tablename__ = "fn_user_expenses"
    __table_args__ = (Index("ix_fn_user_expenses_user_recorded_on", "user_id", "recorded_on"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Numeric en vez de float, mismo motivo que weight_kg en weights.py: evita
    # error de redondeo binario. Alcanza sin problema para montos en COP.
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_method_id: Mapped[int] = mapped_column(
        ForeignKey("fn_payment_methods.id"), nullable=False
    )
    category_id: Mapped[int] = mapped_column(ForeignKey("fn_categories.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # lazy="joined"/"selectin" para que listar gastos no dispare N+1: el
    # service arma ExpenseRead directo desde estos objetos ya resueltos.
    category: Mapped[Category] = relationship(lazy="joined")
    payment_method: Mapped[PaymentMethod] = relationship(lazy="joined")
    tags: Mapped[list[Tag]] = relationship(secondary="fn_expenses_tags", lazy="selectin")


class ExpenseTag(Base):
    """Relacion muchos-a-muchos entre gastos y tags. Sin id propio: la
    identidad de la fila es el par (expense_id, tag_id)."""

    __tablename__ = "fn_expenses_tags"

    expense_id: Mapped[int] = mapped_column(ForeignKey("fn_user_expenses.id"), primary_key=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("fn_user_tags.id"), primary_key=True)
