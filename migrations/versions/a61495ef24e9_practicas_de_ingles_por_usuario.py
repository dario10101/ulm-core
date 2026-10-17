"""practicas de ingles por usuario

Revision ID: a61495ef24e9
Revises: d5fe720bae38
Create Date: 2026-10-17

Fase 2 del modulo English (ENGLISH-TEACHER-PLAN.md): datos de cada usuario.
- eng_user_settings: su nivel y el "no por ahora" de la sugerencia de nivel.
- eng_practices: practicas completadas (se guardan enteras al cierre, D8/D21).
- eng_user_words: relacion usuario-palabra con el check "la domino" (D4).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a61495ef24e9"
down_revision: str | Sequence[str] | None = "d5fe720bae38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

LEVELS = "('A1', 'A2', 'B1', 'B2', 'C1', 'C2')"


def upgrade() -> None:
    op.create_table(
        "eng_user_settings",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=2), nullable=False),
        sa.Column("level_suggestion_dismissed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"level IN {LEVELS}", name=op.f("ck_eng_user_settings_level")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_eng_user_settings_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_eng_user_settings")),
    )
    op.create_table(
        "eng_user_words",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("mastered", sa.Boolean(), nullable=False),
        sa.Column("times_practiced", sa.Integer(), nullable=False),
        sa.Column("last_practiced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mastered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_eng_user_words_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["word_id"], ["eng_words.id"], name=op.f("fk_eng_user_words_word_id_eng_words")
        ),
        sa.PrimaryKeyConstraint("user_id", "word_id", name=op.f("pk_eng_user_words")),
    )
    op.create_table(
        "eng_practices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("word_id", sa.Integer(), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("level", sa.String(length=2), nullable=False),
        sa.Column("vocab_revealed", sa.Boolean(), nullable=False),
        sa.Column("vocab_used_synonym", sa.Boolean(), nullable=False),
        sa.Column("listening_text_shown", sa.Boolean(), nullable=False),
        sa.Column("writing_text", sa.Text(), nullable=False),
        sa.Column("reading_transcript", sa.Text(), nullable=True),
        sa.Column("reading_match_pct", sa.Float(), nullable=True),
        sa.Column("free_transcript", sa.Text(), nullable=True),
        sa.Column("speaking_skipped", sa.Boolean(), nullable=False),
        sa.Column("audio_seconds", sa.Float(), nullable=False),
        sa.Column("was_mastered", sa.Boolean(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(f"level IN {LEVELS}", name=op.f("ck_eng_practices_level")),
        sa.ForeignKeyConstraint(
            ["content_id"],
            ["eng_word_contents.id"],
            name=op.f("fk_eng_practices_content_id_eng_word_contents"),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_eng_practices_user_id_users")
        ),
        sa.ForeignKeyConstraint(
            ["word_id"], ["eng_words.id"], name=op.f("fk_eng_practices_word_id_eng_words")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_eng_practices")),
    )
    op.create_index(op.f("ix_eng_practices_user_id"), "eng_practices", ["user_id"])


def downgrade() -> None:
    op.drop_table("eng_practices")
    op.drop_table("eng_user_words")
    op.drop_table("eng_user_settings")
