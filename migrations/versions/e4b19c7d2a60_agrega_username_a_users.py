"""agrega username a users

Revision ID: e4b19c7d2a60
Revises: d7a2f4c81e35
Create Date: 2026-10-04

Nombre publico del usuario: URL de su blog (/blog/<username>) y, a futuro,
usuario del login con contraseña. Nulo para todos los existentes: cada uno lo
crea desde Settings. Unico sin distinguir mayusculas, igual que el email.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e4b19c7d2a60"
down_revision: str | Sequence[str] | None = "d7a2f4c81e35"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("username", sa.String(length=30), nullable=True))
    op.create_index(
        "uq_users_username", "users", [sa.text("lower(username)")], unique=True
    )


def downgrade() -> None:
    op.drop_index("uq_users_username", table_name="users")
    op.drop_column("users", "username")
