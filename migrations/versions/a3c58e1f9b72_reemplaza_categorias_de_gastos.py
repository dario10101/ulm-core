"""reemplaza las categorias de gastos por las de la app anterior

Revision ID: a3c58e1f9b72
Revises: e4b19c7d2a60
Create Date: 2026-10-04

Migracion de datos (no de esquema): cambia el catalogo sembrado en
31bdd71b624a por las categorias que el usuario ya usaba en su app de gastos
anterior (ulm-data/expenses/app-categories.jpeg), con los mismos nombres.

Sigue la regla de borrado hibrido de los catalogos (ver app/db/models/finance.py):
una categoria con gastos no se borra, se archiva (DISABLED) para no romper la
FK ni perder la referencia historica; las demas se borran de verdad.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c58e1f9b72"
down_revision: str | Sequence[str] | None = "e4b19c7d2a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (nombre, icon_key, color_key). Nombres tal cual la app anterior; iconos y
# colores adaptados a los diccionarios de ulm-web/src/config/financeVisuals.ts.
NEW_CATEGORIES = [
    ("Health", "heart-pulse", "red"),
    ("Leisure", "ticket", "green"),
    ("Apartment", "building", "blue"),
    ("Food", "utensils", "yellow"),
    ("Education", "graduation-cap", "pink"),
    ("Gifts", "gift", "emerald"),
    ("Groceries", "shopping-basket", "sky"),
    ("Family", "users", "rose"),
    ("Workout", "dumbbell", "lime"),
    ("Transportation", "bus-front", "indigo"),
    ("Gray Rage", "car", "slate"),
    ("Other", "circle-help", "orange"),
    ("BG", "circle-help", "fuchsia"),
    ("Dance", "music", "purple"),
    ("Clothes", "shirt", "cyan"),
    ("Grouth", "trending-up", "teal"),
    ("Personal Presentation", "scissors", "violet"),
    ("Subs", "smartphone", "amber"),
    ("Travels", "plane", "green"),
    ("Credit Card", "credit-card", "blue"),
    ("Car Diy project", "wrench", "sky"),
    ("IA", "sparkles", "fuchsia"),
]

# Copia del seed original (31bdd71b624a) para el downgrade: una migracion no
# debe importar de otra.
OLD_CATEGORIES = [
    ("Groceries", "shopping-cart", "lime"),
    ("Dining out", "utensils", "amber"),
    ("Transportation", "bus", "blue"),
    ("Fuel", "fuel", "orange"),
    ("Housing", "house", "yellow"),
    ("Utilities", "zap", "sky"),
    ("Water", "droplet", "cyan"),
    ("Internet & phone", "wifi", "indigo"),
    ("Subscriptions", "credit-card", "violet"),
    ("Health", "heart-pulse", "rose"),
    ("Insurance", "shield-check", "emerald"),
    ("Education", "graduation-cap", "teal"),
    ("Personal care", "sparkles", "pink"),
    ("Clothing", "shirt", "purple"),
    ("Home maintenance", "wrench", "slate"),
    ("Entertainment", "popcorn", "fuchsia"),
    ("Travel", "plane", "sky"),
    ("Gifts", "gift", "pink"),
    ("Donations", "hand-coins", "rose"),
    ("Pets", "paw-print", "amber"),
    ("Debt payments", "landmark", "red"),
    ("Other", "package", "slate"),
]

categories = sa.table(
    "fn_categories",
    sa.column("name", sa.String),
    sa.column("icon_key", sa.String),
    sa.column("color_key", sa.String),
    sa.column("status", sa.String),
)


def _retire_all_categories() -> None:
    """Archiva las categorias con gastos y borra las que no tienen."""
    op.execute(
        "UPDATE fn_categories SET status = 'DISABLED' "
        "WHERE id IN (SELECT DISTINCT category_id FROM fn_user_expenses)"
    )
    op.execute(
        "DELETE FROM fn_categories "
        "WHERE id NOT IN (SELECT DISTINCT category_id FROM fn_user_expenses)"
    )


def _insert(rows: list[tuple[str, str, str]]) -> None:
    op.bulk_insert(
        categories,
        [
            {"name": name, "icon_key": icon_key, "color_key": color_key, "status": "ENABLED"}
            for name, icon_key, color_key in rows
        ],
    )


def upgrade() -> None:
    _retire_all_categories()
    _insert(NEW_CATEGORIES)


def downgrade() -> None:
    _retire_all_categories()
    _insert(OLD_CATEGORIES)
