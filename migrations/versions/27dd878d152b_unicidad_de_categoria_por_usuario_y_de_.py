"""unicidad de categoria por usuario y de semana abierta

Revision ID: 27dd878d152b
Revises: a8e4ccee81be
Create Date: 2026-09-27

D11: dos reglas que hasta ahora solo validaba el service.

- Un nombre de categoria por usuario, sin distinguir mayusculas y contando
  tambien las DISABLED (dos "Salud" con historia saldrian por separado en
  analytics). Es un indice unico sobre `lower(name)` y no una UNIQUE
  constraint porque en Postgres una constraint no admite expresiones.
- A lo sumo una semana abierta por usuario: indice unico *parcial*, que solo
  incluye las filas con `NOT closed`. Las cerradas se repiten sin limite.

El service sigue validando antes de escribir, para devolver un 409 con un
mensaje claro; esto cubre lo que el service no puede ver, como dos requests
simultaneos que pasan ambos la validacion.

Si la base ya tuviera datos que violen alguna regla, la migracion falla al
crear el indice y no toca nada: hay que limpiarlos a mano primero.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "27dd878d152b"
down_revision: Union[str, Sequence[str], None] = "a8e4ccee81be"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_cl_user_categories_user_id_name",
        "cl_user_categories",
        ["user_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_cl_user_weeks_user_id_open",
        "cl_user_weeks",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("NOT closed"),
    )


def downgrade() -> None:
    op.drop_index("uq_cl_user_weeks_user_id_open", table_name="cl_user_weeks")
    op.drop_index("uq_cl_user_categories_user_id_name", table_name="cl_user_categories")
