"""Modelos ORM del modulo English (ENGLISH-TEACHER-PLAN.md, seccion 6).

Banco compartido (sin user_id; lo llena el admin desde Settings -> System):
- eng_words: una fila por palabra de la lista (D29), con su estado en el banco.
- eng_word_images: candidatas de imagen por palabra; una seleccionada.
- eng_word_contents: frases y textos de la practica, uno por palabra y nivel.
"""

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base_class import Base

# Estados de una palabra en el banco.
# PENDING: importada de la lista, falta imagen o contenido.
# APPROVED: tiene imagen y contenido validos; entra en practicas.
# REVIEW: el llenado fallo (sin imagen, contenido invalido); se reintenta hasta
#   ENGLISH_MAX_FILL_ATTEMPTS veces y despues queda para el admin.
# DISABLED: el admin la saco del banco (curacion posterior, D24).
WORD_PENDING = "PENDING"
WORD_APPROVED = "APPROVED"
WORD_REVIEW = "REVIEW"
WORD_DISABLED = "DISABLED"
WORD_STATUSES = (WORD_PENDING, WORD_APPROVED, WORD_REVIEW, WORD_DISABLED)

LEVEL_CHECK = "IN ('A1', 'A2', 'B1', 'B2', 'C1', 'C2')"


def _now() -> datetime:
    return datetime.now(UTC)


# JSONB en Postgres; JSON en SQLite (tests).
JsonList = JSON().with_variant(JSONB(), "postgresql")


class EngWord(Base):
    __tablename__ = "eng_words"
    __table_args__ = (
        # Una entrada por palabra (D29): la categoria la decide la importacion.
        UniqueConstraint("lemma", name="uq_eng_words_lemma"),
        CheckConstraint(f"cefr_level {LEVEL_CHECK}", name="cefr_level"),
        CheckConstraint("status IN ('PENDING', 'APPROVED', 'REVIEW', 'DISABLED')", name="status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    lemma: Mapped[str] = mapped_column(String(40), nullable=False)
    # noun / verb / adjective
    pos: Mapped[str] = mapped_column(String(20), nullable=False)
    cefr_level: Mapped[str] = mapped_column(String(2), nullable=False, index=True)
    # Formas alternativas de la lista y sinonimos del LLM, ya filtrados al mismo
    # largo y patron que `lemma` (D30): las casillas del front tienen largo fijo.
    accepted_answers: Mapped[list[Any]] = mapped_column(JsonList, nullable=False, default=list)
    # Formas alternativas segun la lista (ej. "colour"), antes de filtrar.
    variants: Mapped[list[Any]] = mapped_column(JsonList, nullable=False, default=list)
    source_list: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default=WORD_PENDING)
    # Por que quedo en REVIEW (ej. "no_image", "word_missing_in_sentence").
    status_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fill_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EngWordImage(Base):
    __tablename__ = "eng_word_images"
    __table_args__ = (UniqueConstraint("word_id", "position", name="uq_eng_word_images_position"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("eng_words.id"), nullable=False, index=True)
    # Orden de preferencia (0 = la primera que devolvieron las fuentes).
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    # arasaac / pexels / openverse
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    license: Mapped[str] = mapped_column(String(120), nullable=False)
    # Texto de credito que exige la licencia; el front lo muestra con la imagen.
    attribution: Mapped[str] = mapped_column(Text, nullable=False)
    page_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    # La que se muestra. Una sola por palabra: lo garantiza el service.
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # El admin la descarto con "cambiar imagen": no vuelve a elegirse.
    rejected: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class EngWordContent(Base):
    __tablename__ = "eng_word_contents"
    __table_args__ = (
        UniqueConstraint("word_id", "level", name="uq_eng_word_contents_word_id_level"),
        CheckConstraint(f"level {LEVEL_CHECK}", name="level"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    word_id: Mapped[int] = mapped_column(ForeignKey("eng_words.id"), nullable=False)
    level: Mapped[str] = mapped_column(String(2), nullable=False)
    listening_sentence: Mapped[str] = mapped_column(Text, nullable=False)
    writing_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    # Solo A1/A2 (instrucciones en español); en los demas niveles, nulo.
    writing_prompt_es: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Empieza con la frase del listening y termina con la pregunta.
    reading_text: Mapped[str] = mapped_column(Text, nullable=False)
    reading_question: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(60), nullable=False)
    # Version del prompt que lo genero: si el prompt cambia, se sabe que
    # contenido es viejo sin compararlo.
    prompt_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
