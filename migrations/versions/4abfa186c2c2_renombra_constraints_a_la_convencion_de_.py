"""renombra constraints a la convencion de nombres

Revision ID: 4abfa186c2c2
Revises: 56b5e7da78de
Create Date: 2026-09-23

Alinea los nombres que Postgres invento (`tabla_pkey`, `tabla_col_fkey`) con la
convencion declarada en `app/db/base_class.py`.

Escrita a mano a proposito: **autogenerate no detecta renombres de
constraints**. De hecho `alembic check` daba "sin cambios" con la convencion ya
puesta y la base todavia con los nombres viejos, porque compara la estructura y
no los nombres. El drift existia pero era invisible, y habria aparecido recien
el dia que una migracion futura intentara borrar un constraint por un nombre
que en la base no existe.

`ALTER TABLE ... RENAME CONSTRAINT` es solo metadata: no reescribe datos ni
revalida la constraint.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "4abfa186c2c2"
down_revision: Union[str, Sequence[str], None] = "56b5e7da78de"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabla, nombre viejo, nombre nuevo)
RENAMES: list[tuple[str, str, str]] = [
    ("cl_categories", "cl_categories_pkey", "pk_cl_categories"),
    ("cl_categories", "cl_categories_user_id_fkey", "fk_cl_categories_user_id_users"),
    ("cl_tasks", "cl_tasks_category_id_fkey", "fk_cl_tasks_category_id_cl_categories"),
    ("cl_tasks", "cl_tasks_cl_week_id_fkey", "fk_cl_tasks_cl_week_id_cl_week"),
    ("cl_tasks", "cl_tasks_pkey", "pk_cl_tasks"),
    (
        "cl_template_tasks",
        "cl_template_tasks_category_id_fkey",
        "fk_cl_template_tasks_category_id_cl_categories",
    ),
    ("cl_template_tasks", "cl_template_tasks_pkey", "pk_cl_template_tasks"),
    ("cl_week", "cl_week_pkey", "pk_cl_week"),
    ("cl_week", "cl_week_user_id_fkey", "fk_cl_week_user_id_users"),
    (
        "cl_week_category_day_score",
        "cl_week_category_day_score_category_id_fkey",
        "fk_cl_week_category_day_score_category_id_cl_categories",
    ),
    (
        "cl_week_category_day_score",
        "cl_week_category_day_score_cl_week_id_fkey",
        "fk_cl_week_category_day_score_cl_week_id_cl_week",
    ),
    (
        "cl_week_category_day_score",
        "cl_week_category_day_score_pkey",
        "pk_cl_week_category_day_score",
    ),
    ("cld_events", "cld_events_pkey", "pk_cld_events"),
    ("cld_tasks", "cld_tasks_category_id_fkey", "fk_cld_tasks_category_id_cl_categories"),
    ("cld_tasks", "cld_tasks_pkey", "pk_cld_tasks"),
    ("cld_tasks", "cld_tasks_user_id_fkey", "fk_cld_tasks_user_id_users"),
    (
        "cld_user_events",
        "cld_user_events_category_id_fkey",
        "fk_cld_user_events_category_id_cl_categories",
    ),
    ("cld_user_events", "cld_user_events_pkey", "pk_cld_user_events"),
    ("cld_user_events", "cld_user_events_user_id_fkey", "fk_cld_user_events_user_id_users"),
    ("dummy", "dummy_pkey", "pk_dummy"),
    ("users", "users_pkey", "pk_users"),
    ("weights", "weights_pkey", "pk_weights"),
    ("weights", "weights_user_id_fkey", "fk_weights_user_id_users"),
]


def _rename(tabla: str, desde: str, hacia: str) -> None:
    # IF EXISTS no aplica a RENAME CONSTRAINT, asi que se consulta el catalogo:
    # una base creada desde cero con la convencion ya puesta llega aca con los
    # nombres nuevos y no hay nada que renombrar.
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = '{desde}'
                  AND conrelid = '{tabla}'::regclass
            ) THEN
                ALTER TABLE {tabla} RENAME CONSTRAINT {desde} TO {hacia};
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    for tabla, viejo, nuevo in RENAMES:
        _rename(tabla, viejo, nuevo)


def downgrade() -> None:
    for tabla, viejo, nuevo in RENAMES:
        _rename(tabla, nuevo, viejo)
