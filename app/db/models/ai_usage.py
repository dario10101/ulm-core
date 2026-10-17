"""Registro transversal del consumo de servicios de IA pagados (ai_usage_events).

Una fila por llamada al proveedor, escrita en el mismo request que la hizo:
es la base del futuro control de creditos por usuario (ENGLISH-TEACHER-PLAN.md,
D6/D7/D23). Se registra al llamar y no al guardar el resultado, porque el
gasto ocurre aunque el usuario despues descarte lo que pidio (ej. recargar la
pagina a mitad de una practica de ingles).
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base


def _now() -> datetime:
    return datetime.now(UTC)


class AiUsageEvent(Base):
    __tablename__ = "ai_usage_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Quien la origino (el admin en el llenado del banco).
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    # Ej. "english.bank", "english.transcription", "english.feedback".
    feature: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Solo transcripcion (se cobra por minuto, no por tokens).
    audio_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Segun los precios informativos del catalogo; la unidad de los creditos (D23).
    estimated_cost_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
