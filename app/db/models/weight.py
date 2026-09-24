"""Modelo ORM de registros de peso corporal."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


class WeightRecord(Base):
    __tablename__ = "weights"
    __table_args__ = (Index("ix_weights_user_recorded_on", "user_id", "recorded_on"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Numeric en vez de Float: evita errores de redondeo binario para un valor
    # exacto (72.4 != 72.400000001)
    weight_kg: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    recorded_on: Mapped[date] = mapped_column(Date, nullable=False)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
