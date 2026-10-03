"""renombra tablas del usuario

Revision ID: 4d0cb87197ac
Revises: 2f90f7eeef16
Create Date: 2026-09-27

Las tablas que pertenecen a un usuario llevan `user` en el nombre, como ya
hacia finanzas (`fn_user_tags`, `fn_user_expenses`). Asi `cl_user_categories`
(por usuario) no se confunde con `fn_categories` (catalogo global).

Escrita a mano: `ALTER TABLE ... RENAME` no arrastra el nombre de lo que cuelga
de la tabla. Secuencia, PK, FK e indices conservan el nombre viejo, y la
convencion de `app/db/base_class.py` deriva todos esos nombres de la tabla.
Autogenerate no ve renombres (propondria DROP + CREATE, perdiendo los datos) y
`alembic check` no compara nombres, asi que el drift quedaria invisible. Ver
`scripts/check_db_names.py`, que si lo detecta.

Todo es solo metadata: no se reescriben datos ni se revalidan constraints. Las
columnas `serial` referencian su secuencia por OID, asi que renombrarla no
rompe el `nextval` del default.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "4d0cb87197ac"
down_revision: Union[str, Sequence[str], None] = "2f90f7eeef16"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (viejo, nuevo). La secuencia y la PK siguen el mismo patron en todas.
TABLAS: list[tuple[str, str]] = [
    ("cl_categories", "cl_user_categories"),
    ("cl_template_tasks", "cl_user_template_tasks"),
    ("cl_week", "cl_user_weeks"),
    ("cld_tasks", "cld_user_tasks"),
    ("meals", "user_meals"),
    ("weights", "user_weights"),
]

# (tabla con su nombre NUEVO, fk vieja, fk nueva). Incluye FK de tablas que no
# se renombran pero apuntan a una que si: el nombre de la FK lleva la tabla
# referenciada.
FKS: list[tuple[str, str, str]] = [
    (
        "cl_user_categories",
        "fk_cl_categories_user_id_users",
        "fk_cl_user_categories_user_id_users",
    ),
    (
        "cl_user_template_tasks",
        "fk_cl_template_tasks_user_id_users",
        "fk_cl_user_template_tasks_user_id_users",
    ),
    (
        "cl_user_template_tasks",
        "fk_cl_template_tasks_category_id_cl_categories",
        "fk_cl_user_template_tasks_category_id_cl_user_categories",
    ),
    ("cl_user_weeks", "fk_cl_week_user_id_users", "fk_cl_user_weeks_user_id_users"),
    ("cld_user_tasks", "fk_cld_tasks_user_id_users", "fk_cld_user_tasks_user_id_users"),
    (
        "cld_user_tasks",
        "fk_cld_tasks_category_id_cl_categories",
        "fk_cld_user_tasks_category_id_cl_user_categories",
    ),
    ("user_meals", "fk_meals_user_id_users", "fk_user_meals_user_id_users"),
    ("user_weights", "fk_weights_user_id_users", "fk_user_weights_user_id_users"),
    # Tablas que conservan su nombre
    (
        "cl_tasks",
        "fk_cl_tasks_category_id_cl_categories",
        "fk_cl_tasks_category_id_cl_user_categories",
    ),
    ("cl_tasks", "fk_cl_tasks_cl_week_id_cl_week", "fk_cl_tasks_cl_week_id_cl_user_weeks"),
    (
        "cl_week_category_day_score",
        "fk_cl_week_category_day_score_category_id_cl_categories",
        "fk_cl_week_category_day_score_category_id_cl_user_categories",
    ),
    (
        "cl_week_category_day_score",
        "fk_cl_week_category_day_score_cl_week_id_cl_week",
        "fk_cl_week_category_day_score_cl_week_id_cl_user_weeks",
    ),
    (
        "cld_user_events",
        "fk_cld_user_events_category_id_cl_categories",
        "fk_cld_user_events_category_id_cl_user_categories",
    ),
]

# Indices con nombre explicito en el modelo (no pasan por la convencion).
INDICES: list[tuple[str, str]] = [
    ("ix_cl_categories_user_priority", "ix_cl_user_categories_user_priority"),
    ("ix_meals_user_recorded_on", "ix_user_meals_user_recorded_on"),
    ("ix_weights_user_recorded_on", "ix_user_weights_user_recorded_on"),
]


def _renombrar_tabla(desde: str, hacia: str) -> None:
    op.rename_table(desde, hacia)
    op.execute(f"ALTER SEQUENCE {desde}_id_seq RENAME TO {hacia}_id_seq")
    op.execute(f"ALTER TABLE {hacia} RENAME CONSTRAINT pk_{desde} TO pk_{hacia}")


def upgrade() -> None:
    for viejo, nuevo in TABLAS:
        _renombrar_tabla(viejo, nuevo)
    for tabla, viejo, nuevo in FKS:
        op.execute(f"ALTER TABLE {tabla} RENAME CONSTRAINT {viejo} TO {nuevo}")
    for viejo, nuevo in INDICES:
        op.execute(f"ALTER INDEX {viejo} RENAME TO {nuevo}")


def downgrade() -> None:
    # Orden inverso: FK e indices primero, mientras las tablas todavia tienen
    # el nombre nuevo que usa la lista FKS.
    for viejo, nuevo in INDICES:
        op.execute(f"ALTER INDEX {nuevo} RENAME TO {viejo}")
    for tabla, viejo, nuevo in FKS:
        op.execute(f"ALTER TABLE {tabla} RENAME CONSTRAINT {nuevo} TO {viejo}")
    for viejo, nuevo in TABLAS:
        _renombrar_tabla(nuevo, viejo)
