"""email unico por usuario y quita la tabla dummy

Revision ID: 27d425cd21f5
Revises: 85e4fcd72b0d
Create Date: 2026-10-03

Preparacion del login (fase 0):

1. `users.email` pasa a ser unico sin distinguir mayusculas: la invitacion y
   el login con Google buscan al usuario por email. Antes del indice se
   normalizan los emails existentes (minusculas, sin espacios), que es como
   los guarda la app de aca en adelante. Si dos usuarios ya compartieran
   email, el indice falla: es un dato a resolver a mano.

2. Se borra `dummy`, la tabla de prueba del acceso a Postgres. No tiene dueño,
   y con login cada ruta tiene que tener uno. El downgrade la recrea vacia.

3. Se alinea la secuencia de `users.id`. El usuario quemado lo creaba la app
   con `id=1` explicito, y un INSERT con id explicito no avanza la secuencia:
   el primer usuario invitado intentaria reusar el id 1 y chocaria con la PK.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "27d425cd21f5"
down_revision: str | Sequence[str] | None = "85e4fcd72b0d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("UPDATE users SET email = lower(trim(email))")
    op.create_index("uq_users_email", "users", [sa.text("lower(email)")], unique=True)

    op.drop_table("dummy")

    # is_called=false: el proximo nextval() devuelve exactamente ese valor.
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('users', 'id'),
            COALESCE((SELECT max(id) FROM users), 0) + 1,
            false
        )
        """
    )


def downgrade() -> None:
    op.create_table(
        "dummy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_dummy"),
    )

    op.drop_index("uq_users_email", table_name="users")
