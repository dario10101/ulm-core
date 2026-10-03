"""renombra cl_tasks a cl_week_tasks

Revision ID: a8e4ccee81be
Revises: 4d0cb87197ac
Create Date: 2026-09-27

`cl_tasks` no es del usuario directamente sino de una semana (llega al usuario
via `cl_week_id`), y el nombre nuevo dice eso. Mismo patron de renombre que
4d0cb87197ac.

Aprovecha para indexar `cl_week_id`: Postgres no crea indices sobre las FK por
si solo (MySQL si), y esta es la tabla que mas crece y siempre se consulta por
semana.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "a8e4ccee81be"
down_revision: Union[str, Sequence[str], None] = "4d0cb87197ac"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

VIEJO = "cl_tasks"
NUEVO = "cl_week_tasks"

# (fk vieja, fk nueva); la tabla referenciada ya la renombro 4d0cb87197ac.
FKS: list[tuple[str, str]] = [
    (
        "fk_cl_tasks_category_id_cl_user_categories",
        "fk_cl_week_tasks_category_id_cl_user_categories",
    ),
    ("fk_cl_tasks_cl_week_id_cl_user_weeks", "fk_cl_week_tasks_cl_week_id_cl_user_weeks"),
]

INDICE_SEMANA = "ix_cl_week_tasks_cl_week_id"


def upgrade() -> None:
    op.rename_table(VIEJO, NUEVO)
    op.execute(f"ALTER SEQUENCE {VIEJO}_id_seq RENAME TO {NUEVO}_id_seq")
    op.execute(f"ALTER TABLE {NUEVO} RENAME CONSTRAINT pk_{VIEJO} TO pk_{NUEVO}")
    for viejo, nuevo in FKS:
        op.execute(f"ALTER TABLE {NUEVO} RENAME CONSTRAINT {viejo} TO {nuevo}")
    op.create_index(INDICE_SEMANA, NUEVO, ["cl_week_id"], unique=False)


def downgrade() -> None:
    op.drop_index(INDICE_SEMANA, table_name=NUEVO)
    for viejo, nuevo in FKS:
        op.execute(f"ALTER TABLE {NUEVO} RENAME CONSTRAINT {nuevo} TO {viejo}")
    op.execute(f"ALTER TABLE {NUEVO} RENAME CONSTRAINT pk_{NUEVO} TO pk_{VIEJO}")
    op.execute(f"ALTER SEQUENCE {NUEVO}_id_seq RENAME TO {VIEJO}_id_seq")
    op.rename_table(NUEVO, VIEJO)
