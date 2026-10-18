"""dictado en practicas de ingles

Revision ID: 0be0a4f3d30b
Revises: a48ff2159e3e
Create Date: 2026-10-17

Fase 1 del writing (ENGLISH-TEACHER-PLAN.md, D33): antes de responder, el
usuario escribe la frase que escucho. Se guarda lo escrito y su coincidencia
con la frase (calculada en el backend). Nulos en las practicas anteriores.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0be0a4f3d30b"
down_revision: str | Sequence[str] | None = "a48ff2159e3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("eng_practices", sa.Column("dictation_text", sa.Text(), nullable=True))
    op.add_column("eng_practices", sa.Column("dictation_match_pct", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("eng_practices", "dictation_match_pct")
    op.drop_column("eng_practices", "dictation_text")
