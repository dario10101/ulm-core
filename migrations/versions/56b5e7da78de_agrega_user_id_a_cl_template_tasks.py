"""agrega user_id a cl_template_tasks

Revision ID: 56b5e7da78de
Revises: cf2ce11c7a8b
Create Date: 2026-09-23 22:25:09.085565

Escrita a mano sobre lo que genero --autogenerate, que proponia dos cosas que
no funcionan:

1. `add_column(..., nullable=False)` sin relleno: falla en cuanto hay una fila
   existente. Se aplica el patron expandir / rellenar / contraer: la columna
   entra nullable, se rellena desde la categoria (que es de donde se derivaba
   la pertenencia hasta ahora) y recien despues se vuelve obligatoria.
2. Un foreign key sin nombre, cuyo `drop_constraint(None)` del downgrade
   fallaria. Se le pone nombre explicito (ver la deuda D18: falta una
   convencion de nombres para no tener que acordarse de esto cada vez).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "56b5e7da78de"
down_revision: Union[str, Sequence[str], None] = "cf2ce11c7a8b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_NAME = "fk_cl_template_tasks_user_id_users"


def upgrade() -> None:
    # 1. Expandir: nullable, para no romper las filas que ya existen.
    op.add_column("cl_template_tasks", sa.Column("user_id", sa.Integer(), nullable=True))

    # 2. Rellenar: hasta ahora el dueño se derivaba por join con la categoria,
    #    asi que esa es la fuente de verdad para los datos historicos.
    op.execute(
        """
        UPDATE cl_template_tasks AS t
        SET user_id = c.user_id
        FROM cl_categories AS c
        WHERE c.id = t.category_id
        """
    )

    # 3. Contraer: ya no puede quedar ninguna sin dueño.
    op.alter_column("cl_template_tasks", "user_id", nullable=False)
    op.create_foreign_key(FK_NAME, "cl_template_tasks", "users", ["user_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint(FK_NAME, "cl_template_tasks", type_="foreignkey")
    op.drop_column("cl_template_tasks", "user_id")
