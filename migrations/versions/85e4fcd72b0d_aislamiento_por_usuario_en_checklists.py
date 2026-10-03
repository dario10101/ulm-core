"""aislamiento por usuario en checklists y calendario

Revision ID: 85e4fcd72b0d
Revises: 624cd8c6be83
Create Date: 2026-10-03

Dos cambios, ambos para que la pertenencia de una fila a un usuario la
garantice la base y no solo el codigo:

1. `cl_week_tasks` y `cl_week_category_day_score` reciben su propio `user_id`
   (desnormalizado: hasta ahora se derivaba de la semana). Patron expandir /
   rellenar / contraer (ver 56b5e7da78de_agrega_user_id_a_cl_template_tasks):
   entra nullable, se rellena desde `cl_user_weeks` y recien despues pasa a
   NOT NULL.

2. Las FK simples hacia la categoria (y hacia la semana, en las dos tablas
   de arriba) se reemplazan por FK compuestas:
       FOREIGN KEY (user_id, category_id) -> cl_user_categories (user_id, id)
       FOREIGN KEY (user_id, cl_week_id)  -> cl_user_weeks      (user_id, id)
   Una FK compuesta exige que exista una fila padre con *ese par*, asi que una
   tarea no puede apuntar a la categoria (o semana) de otro usuario. Para que
   Postgres acepte la referencia, el padre necesita UNIQUE (user_id, id):
   redundante como unicidad (id ya es PK), pero es el requisito de la FK.

   La FK compuesta implica a la simple (si existe el par, existe el id), por
   eso la simple se borra en vez de convivir con la nueva.

Si la base ya tuviera una referencia cruzada entre usuarios, el paso 2 falla
con el par exacto que no existe: es un dato a corregir a mano, no algo que la
migracion deba adivinar.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "85e4fcd72b0d"
down_revision: str | Sequence[str] | None = "624cd8c6be83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Tablas hijas de la semana que reciben user_id propio.
WEEK_CHILDREN = ("cl_week_tasks", "cl_week_category_day_score")

# Tablas cuya category_id pasa a FK compuesta.
CATEGORY_CHILDREN = (
    "cl_user_template_tasks",
    "cl_week_tasks",
    "cl_week_category_day_score",
    "cld_user_tasks",
    "cld_user_events",
)

PARENT_UNIQUES = {
    "cl_user_categories": "uq_cl_user_categories_user_id_id",
    "cl_user_weeks": "uq_cl_user_weeks_user_id_id",
}


def _category_fk(table: str) -> tuple[str, str]:
    """(nombre viejo, nombre nuevo), segun la convencion de app/db/base_class.py."""
    return (
        f"fk_{table}_category_id_cl_user_categories",
        f"fk_{table}_user_id_cl_user_categories",
    )


def _week_fk(table: str) -> tuple[str, str]:
    return f"fk_{table}_cl_week_id_cl_user_weeks", f"fk_{table}_user_id_cl_user_weeks"


def upgrade() -> None:
    # 1. user_id propio en las hijas de la semana.
    for table in WEEK_CHILDREN:
        op.add_column(table, sa.Column("user_id", sa.Integer(), nullable=True))
        op.execute(
            f"""
            UPDATE {table} AS child
            SET user_id = w.user_id
            FROM cl_user_weeks AS w
            WHERE w.id = child.cl_week_id
            """
        )
        op.alter_column(table, "user_id", nullable=False)

    # 2. Destinos de las FK compuestas.
    for table, name in PARENT_UNIQUES.items():
        op.create_unique_constraint(name, table, ["user_id", "id"])

    # 3. FK simples -> compuestas.
    for table in CATEGORY_CHILDREN:
        old_name, new_name = _category_fk(table)
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(
            new_name, table, "cl_user_categories", ["user_id", "category_id"], ["user_id", "id"]
        )

    for table in WEEK_CHILDREN:
        old_name, new_name = _week_fk(table)
        op.drop_constraint(old_name, table, type_="foreignkey")
        op.create_foreign_key(
            new_name, table, "cl_user_weeks", ["user_id", "cl_week_id"], ["user_id", "id"]
        )


def downgrade() -> None:
    for table in WEEK_CHILDREN:
        old_name, new_name = _week_fk(table)
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(old_name, table, "cl_user_weeks", ["cl_week_id"], ["id"])

    for table in CATEGORY_CHILDREN:
        old_name, new_name = _category_fk(table)
        op.drop_constraint(new_name, table, type_="foreignkey")
        op.create_foreign_key(old_name, table, "cl_user_categories", ["category_id"], ["id"])

    for table, name in PARENT_UNIQUES.items():
        op.drop_constraint(name, table, type_="unique")

    for table in WEEK_CHILDREN:
        op.drop_column(table, "user_id")
