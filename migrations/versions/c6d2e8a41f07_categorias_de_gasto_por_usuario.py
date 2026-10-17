"""categorias de gasto por usuario

Revision ID: c6d2e8a41f07
Revises: ebddf5bc354d
Create Date: 2026-10-06

Las categorias de gasto dejan de ser un catalogo global:

- `fn_user_expenses_categories` (nueva): las categorias de cada usuario, con
  el mismo borrado hibrido que tags (ENABLED/DISABLED).
- `fn_categories` pasa a ser `fn_default_expense_categories`: la plantilla que
  se copia a cada usuario nuevo al registrarse. Ya nada la referencia, asi que
  pierde `status` (no se archiva, se borra).

Migracion de datos: cada usuario existente recibe una copia de las categorias
ENABLED, mas las archivadas que sus propios gastos usen (con su status). Los
gastos se reapuntan a la copia de su dueño por nombre.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c6d2e8a41f07"
down_revision: str | Sequence[str] | None = "ebddf5bc354d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "fn_user_expenses_categories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("icon_key", sa.String(length=60), nullable=False),
        sa.Column("color_key", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ENABLED", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_fn_user_expenses_categories_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fn_user_expenses_categories"),
        sa.UniqueConstraint(
            "user_id", "name", name="uq_fn_user_expenses_categories_user_id_name"
        ),
    )

    op.execute(
        """
        INSERT INTO fn_user_expenses_categories (user_id, name, icon_key, color_key, status)
        SELECT u.id, c.name, c.icon_key, c.color_key, c.status
        FROM users u
        JOIN fn_categories c
          ON c.status = 'ENABLED'
          OR c.id IN (SELECT e.category_id FROM fn_user_expenses e WHERE e.user_id = u.id)
        ORDER BY u.id, c.id
        """
    )

    op.drop_constraint(
        "fk_fn_user_expenses_category_id_fn_categories", "fn_user_expenses", type_="foreignkey"
    )
    op.execute(
        """
        UPDATE fn_user_expenses e
        SET category_id = uc.id
        FROM fn_categories c, fn_user_expenses_categories uc
        WHERE c.id = e.category_id AND uc.user_id = e.user_id AND uc.name = c.name
        """
    )
    op.create_foreign_key(
        "fk_fn_user_expenses_category_id_fn_user_expenses_categories",
        "fn_user_expenses",
        "fn_user_expenses_categories",
        ["category_id"],
        ["id"],
    )

    # La plantilla solo guarda lo que se le ofrece a un usuario nuevo.
    op.execute("DELETE FROM fn_categories WHERE status <> 'ENABLED'")
    op.drop_column("fn_categories", "status")
    op.rename_table("fn_categories", "fn_default_expense_categories")
    op.execute(
        "ALTER TABLE fn_default_expense_categories "
        "RENAME CONSTRAINT pk_fn_categories TO pk_fn_default_expense_categories"
    )
    op.execute(
        "ALTER SEQUENCE fn_categories_id_seq RENAME TO fn_default_expense_categories_id_seq"
    )


def downgrade() -> None:
    op.execute(
        "ALTER SEQUENCE fn_default_expense_categories_id_seq RENAME TO fn_categories_id_seq"
    )
    op.execute(
        "ALTER TABLE fn_default_expense_categories "
        "RENAME CONSTRAINT pk_fn_default_expense_categories TO pk_fn_categories"
    )
    op.rename_table("fn_default_expense_categories", "fn_categories")
    op.add_column(
        "fn_categories",
        sa.Column("status", sa.String(length=20), server_default="ENABLED", nullable=False),
    )

    # Lo que los usuarios crearon por su cuenta vuelve al catalogo global
    # (archivado: no era de todos). Un nombre repetido entre usuarios queda una vez.
    op.execute(
        """
        INSERT INTO fn_categories (name, icon_key, color_key, status)
        SELECT DISTINCT ON (uc.name) uc.name, uc.icon_key, uc.color_key, 'DISABLED'
        FROM fn_user_expenses_categories uc
        WHERE uc.name NOT IN (SELECT name FROM fn_categories)
        ORDER BY uc.name, uc.id
        """
    )

    op.drop_constraint(
        "fk_fn_user_expenses_category_id_fn_user_expenses_categories",
        "fn_user_expenses",
        type_="foreignkey",
    )
    op.execute(
        """
        UPDATE fn_user_expenses e
        SET category_id = c.id
        FROM fn_user_expenses_categories uc, fn_categories c
        WHERE uc.id = e.category_id AND c.name = uc.name
        """
    )
    op.create_foreign_key(
        "fk_fn_user_expenses_category_id_fn_categories",
        "fn_user_expenses",
        "fn_categories",
        ["category_id"],
        ["id"],
    )
    op.drop_table("fn_user_expenses_categories")
