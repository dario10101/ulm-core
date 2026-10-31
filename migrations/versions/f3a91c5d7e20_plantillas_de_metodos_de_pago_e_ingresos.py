"""plantillas por defecto de metodos de pago y de fuentes/subcategorias de ingreso

Revision ID: f3a91c5d7e20
Revises: ccde87bec443
Create Date: 2026-10-31

Mismo concepto que las categorias de gasto (c6d2e8a41f07): una tabla
`fn_default_*` es la plantilla que se copia a cada usuario al registrarse, y
la tabla `fn_user_*` guarda lo de cada usuario.

- Metodos de pago: dejan de ser globales. `fn_user_payment_methods` (nueva)
  recibe, por usuario, los ENABLED mas los archivados que sus gastos usen; los
  gastos se reapuntan por nombre. `fn_payment_methods` pasa a ser la plantilla
  `fn_default_payment_methods`, sin `status` (no se archiva, se borra).
- Ingresos: fuentes y subcategorias ya eran por usuario. Se agregan las
  plantillas `fn_default_sources` y `fn_default_subcategories`, sembradas con
  un contenido generico minimo. No se copian a usuarios existentes (decision
  explicita: solo aplican a usuarios nuevos).
- Se corrige el nombre `fn_default_expense_categories` a
  `fn_default_expenses_categories`, en linea con `fn_user_expenses_categories`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f3a91c5d7e20"
down_revision: str | Sequence[str] | None = "ccde87bec443"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (nombre, tipo, subcategorias). Generico a proposito: el admin lo ajusta en
# Settings. Una fuente de cada tipo para que ningun formulario arranque vacio.
DEFAULT_SOURCES = [
    ("Salary", "DIRECT", ["BASE SALARY", "BONUS", "OTHER"]),
    ("Savings account", "INTEREST", ["MAIN"]),
]


def _rename_table(old: str, new: str) -> None:
    """Tabla + su PK y su secuencia, para que los nombres sigan la convencion."""
    op.rename_table(old, new)
    op.execute(f"ALTER TABLE {new} RENAME CONSTRAINT pk_{old} TO pk_{new}")
    op.execute(f"ALTER SEQUENCE {old}_id_seq RENAME TO {new}_id_seq")


def upgrade() -> None:
    _rename_table("fn_default_expense_categories", "fn_default_expenses_categories")

    # --- Metodos de pago por usuario ---
    op.create_table(
        "fn_user_payment_methods",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("icon_key", sa.String(length=60), nullable=False),
        sa.Column("color_key", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="ENABLED", nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_fn_user_payment_methods_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fn_user_payment_methods"),
        sa.UniqueConstraint("user_id", "name", name="uq_fn_user_payment_methods_user_id_name"),
    )
    op.execute(
        """
        INSERT INTO fn_user_payment_methods (user_id, name, icon_key, color_key, status)
        SELECT u.id, p.name, p.icon_key, p.color_key, p.status
        FROM users u
        JOIN fn_payment_methods p
          ON p.status = 'ENABLED'
          OR p.id IN (SELECT e.payment_method_id FROM fn_user_expenses e WHERE e.user_id = u.id)
        ORDER BY u.id, p.id
        """
    )
    op.drop_constraint(
        "fk_fn_user_expenses_payment_method_id_fn_payment_methods",
        "fn_user_expenses",
        type_="foreignkey",
    )
    op.execute(
        """
        UPDATE fn_user_expenses e
        SET payment_method_id = up.id
        FROM fn_payment_methods p, fn_user_payment_methods up
        WHERE p.id = e.payment_method_id AND up.user_id = e.user_id AND up.name = p.name
        """
    )
    op.create_foreign_key(
        "fk_fn_user_expenses_payment_method_id_fn_user_payment_methods",
        "fn_user_expenses",
        "fn_user_payment_methods",
        ["payment_method_id"],
        ["id"],
    )
    op.execute("DELETE FROM fn_payment_methods WHERE status <> 'ENABLED'")
    op.drop_column("fn_payment_methods", "status")
    _rename_table("fn_payment_methods", "fn_default_payment_methods")

    # --- Plantillas de ingreso ---
    sources = op.create_table(
        "fn_default_sources",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_fn_default_sources"),
        sa.UniqueConstraint("name", name="uq_fn_default_sources_name"),
    )
    subcategories = op.create_table(
        "fn_default_subcategories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["fn_default_sources.id"],
            name="fk_fn_default_subcategories_source_id_fn_default_sources",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_fn_default_subcategories"),
        sa.UniqueConstraint(
            "source_id", "name", name="uq_fn_default_subcategories_source_id_name"
        ),
    )
    connection = op.get_bind()
    for name, type_, subcategory_names in DEFAULT_SOURCES:
        source_id = connection.execute(
            sources.insert().values(name=name, type=type_).returning(sources.c.id)
        ).scalar_one()
        connection.execute(
            subcategories.insert(),
            [{"source_id": source_id, "name": sub} for sub in subcategory_names],
        )


def downgrade() -> None:
    op.drop_table("fn_default_subcategories")
    op.drop_table("fn_default_sources")

    _rename_table("fn_default_payment_methods", "fn_payment_methods")
    op.add_column(
        "fn_payment_methods",
        sa.Column("status", sa.String(length=20), server_default="ENABLED", nullable=False),
    )
    # Lo que los usuarios crearon por su cuenta vuelve al catalogo global
    # (archivado: no era de todos). Un nombre repetido entre usuarios queda una vez.
    op.execute(
        """
        INSERT INTO fn_payment_methods (name, icon_key, color_key, status)
        SELECT DISTINCT ON (up.name) up.name, up.icon_key, up.color_key, 'DISABLED'
        FROM fn_user_payment_methods up
        WHERE up.name NOT IN (SELECT name FROM fn_payment_methods)
        ORDER BY up.name, up.id
        """
    )
    op.drop_constraint(
        "fk_fn_user_expenses_payment_method_id_fn_user_payment_methods",
        "fn_user_expenses",
        type_="foreignkey",
    )
    op.execute(
        """
        UPDATE fn_user_expenses e
        SET payment_method_id = p.id
        FROM fn_user_payment_methods up, fn_payment_methods p
        WHERE up.id = e.payment_method_id AND p.name = up.name
        """
    )
    op.create_foreign_key(
        "fk_fn_user_expenses_payment_method_id_fn_payment_methods",
        "fn_user_expenses",
        "fn_payment_methods",
        ["payment_method_id"],
        ["id"],
    )
    op.drop_table("fn_user_payment_methods")

    _rename_table("fn_default_expenses_categories", "fn_default_expense_categories")
