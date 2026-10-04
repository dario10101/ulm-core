"""permisos de dominio por usuario

Revision ID: 49000e7cce00
Revises: 5358e45d9829
Create Date: 2026-10-03

Fase 3 (autorizacion por modulos). Solo permisos de dominio: el admin no se
guarda aca, sale de ADMIN_EMAILS (ver app/services/permissions.py). Por eso no
hace falta sembrar nada: los usuarios existentes quedan sin permisos y el admin
los tiene todos por configuracion.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "49000e7cce00"
down_revision: str | Sequence[str] | None = "5358e45d9829"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_permissions",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission", sa.String(length=40), nullable=False),
        sa.Column("granted_by", sa.Integer(), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_user_permissions_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["granted_by"], ["users.id"], name="fk_user_permissions_granted_by_users"
        ),
        sa.PrimaryKeyConstraint("user_id", "permission", name="pk_user_permissions"),
    )


def downgrade() -> None:
    op.drop_table("user_permissions")
