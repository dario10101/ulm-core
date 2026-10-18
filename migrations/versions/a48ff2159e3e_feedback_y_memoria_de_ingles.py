"""feedback y memoria de ingles

Revision ID: a48ff2159e3e
Revises: a61495ef24e9
Create Date: 2026-10-17

Fase 5 del modulo English (ENGLISH-TEACHER-PLAN.md, 7.2):
- eng_practice_feedback: el feedback del LLM por practica, guardado para
  volver a verlo sin pagar de nuevo.
- eng_user_memory: resumen corto por usuario que el feedback reescribe; es la
  "memoria" sin contexto en el proveedor.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a48ff2159e3e"
down_revision: str | Sequence[str] | None = "a61495ef24e9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "eng_user_memory",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_eng_user_memory_user_id_users")
        ),
        sa.PrimaryKeyConstraint("user_id", name=op.f("pk_eng_user_memory")),
    )
    op.create_table(
        "eng_practice_feedback",
        sa.Column("practice_id", sa.Integer(), nullable=False),
        sa.Column("feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("model", sa.String(length=60), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["practice_id"],
            ["eng_practices.id"],
            name=op.f("fk_eng_practice_feedback_practice_id_eng_practices"),
        ),
        sa.PrimaryKeyConstraint("practice_id", name=op.f("pk_eng_practice_feedback")),
    )


def downgrade() -> None:
    op.drop_table("eng_practice_feedback")
    op.drop_table("eng_user_memory")
