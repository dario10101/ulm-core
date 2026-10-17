"""banco de ingles y consumo de ia

Revision ID: d5fe720bae38
Revises: 4c07b2a15e70
Create Date: 2026-10-17

Fase 1 del modulo English (ENGLISH-TEACHER-PLAN.md): el banco compartido
(eng_words, eng_word_images, eng_word_contents), sin user_id porque es de toda
la app (D14), y el registro transversal de consumo de IA (ai_usage_events),
base del futuro control de creditos (D6/D7).

Sin datos: el banco lo llena el admin desde Settings -> System -> English bank.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d5fe720bae38"
down_revision: str | Sequence[str] | None = "4c07b2a15e70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEVELS = "('A1', 'A2', 'B1', 'B2', 'C1', 'C2')"


def upgrade() -> None:
    op.create_table(
        "eng_words",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lemma", sa.String(length=40), nullable=False),
        sa.Column("pos", sa.String(length=20), nullable=False),
        sa.Column("cefr_level", sa.String(length=2), nullable=False),
        sa.Column("accepted_answers", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("variants", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("source_list", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("status_reason", sa.String(length=200), nullable=True),
        sa.Column("fill_attempts", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"cefr_level IN {LEVELS}", name=op.f("ck_eng_words_cefr_level")),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'REVIEW', 'DISABLED')",
            name=op.f("ck_eng_words_status"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eng_words")),
        sa.UniqueConstraint("lemma", name="uq_eng_words_lemma"),
    )
    op.create_index(op.f("ix_eng_words_cefr_level"), "eng_words", ["cefr_level"])

    op.create_table(
        "eng_word_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=False),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("license", sa.String(length=120), nullable=False),
        sa.Column("attribution", sa.Text(), nullable=False),
        sa.Column("page_url", sa.String(length=1000), nullable=True),
        sa.Column("selected", sa.Boolean(), nullable=False),
        sa.Column("rejected", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["word_id"], ["eng_words.id"], name=op.f("fk_eng_word_images_word_id_eng_words")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eng_word_images")),
        sa.UniqueConstraint("word_id", "position", name="uq_eng_word_images_position"),
    )
    op.create_index(op.f("ix_eng_word_images_word_id"), "eng_word_images", ["word_id"])

    op.create_table(
        "eng_word_contents",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=2), nullable=False),
        sa.Column("listening_sentence", sa.Text(), nullable=False),
        sa.Column("writing_prompt", sa.Text(), nullable=False),
        sa.Column("writing_prompt_es", sa.Text(), nullable=True),
        sa.Column("reading_text", sa.Text(), nullable=False),
        sa.Column("reading_question", sa.Text(), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("prompt_version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"level IN {LEVELS}", name=op.f("ck_eng_word_contents_level")),
        sa.ForeignKeyConstraint(
            ["word_id"], ["eng_words.id"], name=op.f("fk_eng_word_contents_word_id_eng_words")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eng_word_contents")),
        sa.UniqueConstraint("word_id", "level", name="uq_eng_word_contents_word_id_level"),
    )

    op.create_table(
        "ai_usage_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("feature", sa.String(length=40), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("audio_seconds", sa.Float(), nullable=True),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_ai_usage_events_user_id_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ai_usage_events")),
    )
    op.create_index(op.f("ix_ai_usage_events_user_id"), "ai_usage_events", ["user_id"])


def downgrade() -> None:
    op.drop_table("ai_usage_events")
    op.drop_table("eng_word_contents")
    op.drop_table("eng_word_images")
    op.drop_table("eng_words")
