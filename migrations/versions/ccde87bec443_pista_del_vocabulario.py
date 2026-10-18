"""pista del vocabulario

Revision ID: ccde87bec443
Revises: 0be0a4f3d30b
Create Date: 2026-10-17

Pista del paso de vocabulario (ENGLISH-TEACHER-PLAN.md, D34):
- eng_word_contents.hint: la genera el LLM con el resto del contenido
  (PROMPT_VERSION 2). Nula en el contenido anterior; el de dev se completo a
  mano con un script de una sola vez.
- eng_practices.vocab_hint_used: si el usuario pidio la pista. Las practicas
  existentes quedan en false (server_default: la columna no admite nulos).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ccde87bec443"
down_revision: str | Sequence[str] | None = "0be0a4f3d30b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("eng_word_contents", sa.Column("hint", sa.Text(), nullable=True))
    op.add_column(
        "eng_practices",
        sa.Column("vocab_hint_used", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("eng_practices", "vocab_hint_used")
    op.drop_column("eng_word_contents", "hint")
