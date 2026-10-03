"""quita indices duplicados sobre las pk

Revision ID: 2f90f7eeef16
Revises: a271025b8c49
Create Date: 2026-09-27

Todos los modelos declaraban `mapped_column(primary_key=True, index=True)`. La
PK ya crea su propio indice unico; `index=True` agregaba **otro** indice
identico sobre la misma columna (`ix_<tabla>_id`). No acelera ninguna consulta
y se paga en cada INSERT/UPDATE. El patron viene del tutorial de FastAPI.

Va antes de los renombres de tablas para no renombrar indices que igual se
iban a borrar.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "2f90f7eeef16"
down_revision: Union[str, Sequence[str], None] = "a271025b8c49"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (tabla, indice redundante), con los nombres de esta revision: las tablas
# todavia no se renombraron.
INDICES: list[tuple[str, str]] = [
    ("cl_categories", "ix_cl_categories_id"),
    ("cl_tasks", "ix_cl_tasks_id"),
    ("cl_template_tasks", "ix_cl_template_tasks_id"),
    ("cl_week", "ix_cl_week_id"),
    ("cl_week_category_day_score", "ix_cl_week_category_day_score_id"),
    ("cld_events", "ix_cld_events_id"),
    ("cld_tasks", "ix_cld_tasks_id"),
    ("cld_user_events", "ix_cld_user_events_id"),
    ("dummy", "ix_dummy_id"),
    ("fn_categories", "ix_fn_categories_id"),
    ("fn_payment_methods", "ix_fn_payment_methods_id"),
    ("fn_user_expenses", "ix_fn_user_expenses_id"),
    ("fn_user_tags", "ix_fn_user_tags_id"),
    ("meals", "ix_meals_id"),
    ("users", "ix_users_id"),
    ("weights", "ix_weights_id"),
]


def upgrade() -> None:
    for tabla, indice in INDICES:
        op.drop_index(indice, table_name=tabla)


def downgrade() -> None:
    for tabla, indice in INDICES:
        op.create_index(indice, tabla, ["id"], unique=False)
