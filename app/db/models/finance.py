"""Modelos ORM del modulo de finanzas: catalogos (categorias, metodos de
pago, tags) y registros de gasto.

Categorias y metodos de pago son catalogos globales (no dependen del
usuario); tags, fuentes y subcategorias son por usuario. Todos tienen `status`
(ENABLED/DISABLED): un item con registros no se borra, se archiva (DISABLED),
para no perder la referencia historica; uno sin registros si se borra de
verdad (ver FinanceParamsService / SystemParamsService).
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base_class import Base


class Category(Base):
    __tablename__ = "fn_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
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

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    icon_key: Mapped[str] = mapped_column(String(60), nullable=False)
    color_key: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ENABLED", server_default="ENABLED"
    )


class Tag(Base):
    __tablename__ = "fn_user_tags"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_fn_user_tags_user_id_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    color_key: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ENABLED", server_default="ENABLED"
    )


class Expense(Base):
    __tablename__ = "fn_user_expenses"
    __table_args__ = (Index("ix_fn_user_expenses_user_recorded_on", "user_id", "recorded_on"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    # Numeric en vez de float, mismo motivo que weight_kg en weight.py: evita
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


# --- Ingresos ---
#
# Dos tablas de registro separadas (directo e intereses) porque tienen
# granularidad y columnas distintas: el directo es un monto en un dia; el de
# intereses es la conciliacion de un mes de un producto (saldos, aportes,
# retiros). Fuentes y subcategorias son catalogos por usuario compartidos por
# ambas, con `type` indicando a cual aplican (DIRECT / INTEREST / ALL).


class IncomeSource(Base):
    __tablename__ = "fn_user_sources"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_fn_user_sources_user_id_name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Sin CHECK en la base (pedido explicito): el service valida el valor.
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # Mismo soft delete que los demas catalogos: una fuente con ingresos no se
    # borra, se archiva (ver FinanceParamsService.delete_source).
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ENABLED", server_default="ENABLED"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncomeSubcategory(Base):
    """Cada subcategoria pertenece a una sola fuente (ej. "SALARIO BASE" de
    "Salario"). Por eso el nombre es unico por fuente y no por usuario: dos
    fuentes pueden tener cada una su "EXTRA"."""

    __tablename__ = "fn_user_subcategories"
    __table_args__ = (
        UniqueConstraint("source_id", "name", name="uq_fn_user_subcategories_source_id_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("fn_user_sources.id"), nullable=False)
    # Redundante desde que existe source_id (el tipo lo da la fuente); se
    # conserva por ahora, pero ya no se usa para validar.
    type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="ENABLED", server_default="ENABLED"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DirectIncome(Base):
    __tablename__ = "fn_user_direct_incomes"
    __table_args__ = (
        Index("ix_fn_user_direct_incomes_user_recorded_on", "user_id", "recorded_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("fn_user_sources.id"), nullable=False)
    subcategory_id: Mapped[int] = mapped_column(
        ForeignKey("fn_user_subcategories.id"), nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[IncomeSource] = relationship(lazy="joined")
    subcategory: Mapped[IncomeSubcategory] = relationship(lazy="joined")
    tags: Mapped[list[Tag]] = relationship(secondary="fn_direct_incomes_tags", lazy="selectin")


class DirectIncomeTag(Base):
    __tablename__ = "fn_direct_incomes_tags"

    # `income_id` y no `direct_income_id`: con la convencion de nombres el FK
    # pasaria los 63 caracteres que admite Postgres y quedaria truncado.
    income_id: Mapped[int] = mapped_column(
        ForeignKey("fn_user_direct_incomes.id"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("fn_user_tags.id"), primary_key=True)


class InterestIncome(Base):
    """Un mes de un producto de inversion/ahorro. `recorded_on` es siempre el
    dia 1 del mes (el service lo normaliza): el registro es del periodo, no
    de un dia, y asi la unicidad por (fuente, mes) es un constraint simple."""

    __tablename__ = "fn_user_interest_incomes"
    __table_args__ = (
        # Uno por subcategoria y mes: las subcategorias de una fuente de
        # intereses son productos/bolsillos distintos (ej. Tyba "MI CARRO" y
        # "MI RETIRO"), cada uno con su propio saldo. Nombre explicito: el de
        # la convencion pasaria los 63 caracteres de Postgres.
        UniqueConstraint(
            "user_id",
            "source_id",
            "subcategory_id",
            "recorded_on",
            name="uq_fn_user_interest_incomes_subcategory_period",
        ),
        Index("ix_fn_user_interest_incomes_user_recorded_on", "user_id", "recorded_on"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("fn_user_sources.id"), nullable=False)
    # Nombre explicito: el de la convencion mide 64 caracteres (limite de Postgres: 63).
    subcategory_id: Mapped[int] = mapped_column(
        ForeignKey("fn_user_subcategories.id", name="fk_fn_user_interest_incomes_subcategory_id"),
        nullable=False,
    )
    # Interes del mes. Puede ser negativo (un mes malo en un fondo).
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    # Saldos opcionales: en modo manual el usuario puede registrar solo el
    # interes que le reporta el banco, sin conocer los saldos.
    start_of_month_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    end_of_month_amount: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    deposits_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    withdrawals_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), nullable=False, default=0, server_default="0"
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    source: Mapped[IncomeSource] = relationship(lazy="joined")
    subcategory: Mapped[IncomeSubcategory] = relationship(lazy="joined")
    tags: Mapped[list[Tag]] = relationship(secondary="fn_interest_incomes_tags", lazy="selectin")


class InterestIncomeTag(Base):
    __tablename__ = "fn_interest_incomes_tags"

    income_id: Mapped[int] = mapped_column(
        ForeignKey("fn_user_interest_incomes.id"), primary_key=True
    )
    tag_id: Mapped[int] = mapped_column(ForeignKey("fn_user_tags.id"), primary_key=True)
