"""subcategorias de ingreso por fuente

Revision ID: 624cd8c6be83
Revises: ac076711a735
Create Date: 2026-10-01

Cada subcategoria pasa a pertenecer a UNA fuente (`source_id`, NOT NULL) y el
nombre deja de ser unico por usuario para ser unico por fuente.

Con datos existentes no alcanza con rellenar la columna: una misma
subcategoria pudo usarse con varias fuentes (ej. "EXTRA" con "Salario" y con
"Venta ocasional"). Patron expandir / rellenar / contraer (ver
56b5e7da78de_agrega_user_id_a_cl_template_tasks):

1. Se agrega `source_id` nullable y se quita la unicidad (usuario, nombre),
   que impediria crear las copias del paso 2.
2. Por cada subcategoria, por cada fuente con la que se uso en algun ingreso:
   la primera fuente se queda con la fila original; para cada fuente extra se
   crea una copia y se repuntan los ingresos de esa fuente a la copia.
   Las subcategorias sin uso van a la primera fuente del usuario cuyo tipo
   aplica (DIRECT/INTEREST/ALL); si no hay ninguna, se borran.
3. `source_id` NOT NULL + FK + unicidad (fuente, nombre).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "624cd8c6be83"
down_revision: str | Sequence[str] | None = "ac076711a735"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INCOME_TABLES = ("fn_user_direct_incomes", "fn_user_interest_incomes")


def _applies(source_type: str, subcategory_type: str) -> bool:
    return subcategory_type == "ALL" or source_type in (subcategory_type, "ALL")


def upgrade() -> None:
    # 1. Expandir
    with op.batch_alter_table("fn_user_subcategories") as batch_op:
        batch_op.add_column(sa.Column("source_id", sa.Integer(), nullable=True))
        batch_op.drop_constraint("uq_fn_user_subcategories_user_id_name", type_="unique")

    # 2. Rellenar
    conn = op.get_bind()
    subcategories = conn.execute(
        sa.text("SELECT id, user_id, type, name, created_at FROM fn_user_subcategories ORDER BY id")
    ).all()
    sources = conn.execute(
        sa.text("SELECT id, user_id, type FROM fn_user_sources ORDER BY id")
    ).all()
    usage_sql = " UNION ".join(
        f"SELECT DISTINCT subcategory_id, source_id FROM {table}" for table in INCOME_TABLES
    )
    used_with: dict[int, list[int]] = {}
    for subcategory_id, source_id in conn.execute(sa.text(f"{usage_sql} ORDER BY 1, 2")):
        used_with.setdefault(subcategory_id, []).append(source_id)

    for sub in subcategories:
        source_ids = used_with.get(sub.id)
        if not source_ids:
            fallback = next(
                (s.id for s in sources if s.user_id == sub.user_id and _applies(s.type, sub.type)),
                None,
            )
            if fallback is None:
                conn.execute(
                    sa.text("DELETE FROM fn_user_subcategories WHERE id = :id"), {"id": sub.id}
                )
                continue
            source_ids = [fallback]

        first, *others = source_ids
        conn.execute(
            sa.text("UPDATE fn_user_subcategories SET source_id = :source WHERE id = :id"),
            {"source": first, "id": sub.id},
        )
        for source_id in others:
            copy_id = conn.execute(
                sa.text(
                    "INSERT INTO fn_user_subcategories (user_id, source_id, type, name, created_at)"
                    " VALUES (:user_id, :source_id, :type, :name, :created_at) RETURNING id"
                ),
                {
                    "user_id": sub.user_id,
                    "source_id": source_id,
                    "type": sub.type,
                    "name": sub.name,
                    "created_at": sub.created_at,
                },
            ).scalar_one()
            for table in INCOME_TABLES:
                conn.execute(
                    sa.text(
                        f"UPDATE {table} SET subcategory_id = :copy"
                        " WHERE subcategory_id = :original AND source_id = :source"
                    ),
                    {"copy": copy_id, "original": sub.id, "source": source_id},
                )

    # 3. Contraer
    with op.batch_alter_table("fn_user_subcategories") as batch_op:
        batch_op.alter_column("source_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_foreign_key(
            "fk_fn_user_subcategories_source_id_fn_user_sources",
            "fn_user_sources",
            ["source_id"],
            ["id"],
        )
        batch_op.create_unique_constraint(
            "uq_fn_user_subcategories_source_id_name", ["source_id", "name"]
        )


def downgrade() -> None:
    # Inverso del paso 2: las copias con el mismo (usuario, nombre) se funden
    # en la de menor id antes de restaurar la unicidad por usuario.
    conn = op.get_bind()
    duplicates = conn.execute(
        sa.text(
            "SELECT s.id, keep.id AS keep_id FROM fn_user_subcategories s"
            " JOIN (SELECT user_id, name, MIN(id) AS id FROM fn_user_subcategories"
            "       GROUP BY user_id, name) keep"
            " ON keep.user_id = s.user_id AND keep.name = s.name AND keep.id <> s.id"
        )
    ).all()
    for duplicate_id, keep_id in duplicates:
        for table in INCOME_TABLES:
            conn.execute(
                sa.text(f"UPDATE {table} SET subcategory_id = :keep WHERE subcategory_id = :dup"),
                {"keep": keep_id, "dup": duplicate_id},
            )
        conn.execute(
            sa.text("DELETE FROM fn_user_subcategories WHERE id = :id"), {"id": duplicate_id}
        )

    with op.batch_alter_table("fn_user_subcategories") as batch_op:
        batch_op.drop_constraint(
            "fk_fn_user_subcategories_source_id_fn_user_sources", type_="foreignkey"
        )
        batch_op.drop_constraint("uq_fn_user_subcategories_source_id_name", type_="unique")
        batch_op.create_unique_constraint(
            "uq_fn_user_subcategories_user_id_name", ["user_id", "name"]
        )
        batch_op.drop_column("source_id")
