"""agrega blg_entities

Revision ID: 4c07b2a15e70
Revises: c6d2e8a41f07
Create Date: 2026-10-09

Tabla generica llave-valor del blog (decision B11 de PLAN-BLOG.md): config,
secciones, subsecciones, elementos .md y sus cuerpos de cada usuario, en la
particion `USER#<id>`. Ver app/db/models/blog.py y app/repositories/blog_keys.py.

Sin datos: el registro BLOG de cada usuario se crea en su primer acceso al
modulo, y los datos de prueba van por script (B16), no por migracion (D20).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4c07b2a15e70"
down_revision: str | Sequence[str] | None = "c6d2e8a41f07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "blg_entities",
        sa.Column("pk", sa.String(length=40), nullable=False),
        sa.Column("sk", sa.String(length=120), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("entity_type", sa.String(length=10), nullable=False),
        sa.Column("gsi1pk", sa.String(length=120), nullable=True),
        sa.Column("gsi1sk", sa.String(length=120), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('BLOG', 'SECTION', 'GROUP', 'ITEM', 'BODY')",
            name=op.f("ck_blg_entities_entity_type"),
        ),
        sa.CheckConstraint("pk = 'USER#' || user_id", name=op.f("ck_blg_entities_pk_matches_user")),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name=op.f("fk_blg_entities_user_id_users")
        ),
        sa.PrimaryKeyConstraint("pk", "sk", name=op.f("pk_blg_entities")),
        sa.UniqueConstraint("gsi1pk", "gsi1sk", name="uq_blg_entities_gsi1"),
    )


def downgrade() -> None:
    op.drop_table("blg_entities")
