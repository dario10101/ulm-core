"""code en mayusculas en cld_user_events

Revision ID: d7a2f4c81e35
Revises: b3c1e7a90d42
Create Date: 2026-10-04

Los eventos personales pasan a crearse y editarse desde el calendario, con el
tipo (`code`) como texto libre. Se guarda siempre en mayusculas: el schema lo
normaliza y este CHECK lo garantiza en la base. Antes de crearlo se normalizan
las filas existentes, por si alguna se cargo a mano en minusculas.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d7a2f4c81e35"
down_revision: str | Sequence[str] | None = "b3c1e7a90d42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Nombre final explicito (op.f): el mismo que genera la convencion del modelo
# para name="code_upper" (ver app/db/base_class.py).
CONSTRAINT = "ck_cld_user_events_code_upper"


def upgrade() -> None:
    op.execute("UPDATE cld_user_events SET code = upper(code) WHERE code <> upper(code)")
    op.create_check_constraint(op.f(CONSTRAINT), "cld_user_events", "code = upper(code)")


def downgrade() -> None:
    op.drop_constraint(op.f(CONSTRAINT), "cld_user_events", type_="check")
