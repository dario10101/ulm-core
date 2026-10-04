"""status en fuentes y subcategorias de ingreso

Revision ID: b3c1e7a90d42
Revises: 49000e7cce00
Create Date: 2026-10-04

Las fuentes y subcategorias pasan a administrarse desde la UI con el mismo
borrado hibrido que tags y categorias: sin registros se borran, con registros
se archivan (DISABLED). Las filas existentes quedan ENABLED via server_default.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b3c1e7a90d42"
down_revision: str | Sequence[str] | None = "49000e7cce00"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = ("fn_user_sources", "fn_user_subcategories")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(
            table,
            sa.Column("status", sa.String(length=20), server_default="ENABLED", nullable=False),
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "status")
