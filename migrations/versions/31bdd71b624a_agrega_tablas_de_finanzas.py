"""agrega tablas de finanzas

Revision ID: 31bdd71b624a
Revises: 505c9a5f75e4
Create Date: 2026-09-26 15:21:09.251542

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '31bdd71b624a'
down_revision: Union[str, Sequence[str], None] = '505c9a5f75e4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# --- Datos semilla de los catalogos (sin CRUD todavia, ver app/db/models/finance.py) ---
# icon_key calza 1:1 con el nombre kebab-case del icono en @lucide/vue; color_key
# es un nombre de una paleta fija que vive solo en el frontend (financeVisuals.ts).

CATEGORIES_SEED = [
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

PAYMENT_METHODS_SEED = [
    ("Cash", "banknote", "green"),
    ("Bank transfer", "arrow-right-left", "blue"),
    ("Credit card", "credit-card", "violet"),
    ("PSE", "landmark", "indigo"),
]

# user_id=1 es el usuario quemado (settings.default_user_id). Cuando exista
# auth real, sembrar tags por usuario habra que revisarlo.
TAGS_SEED = [
    ("NEEDED", "emerald"),
    ("WANTED", "amber"),
    ("IMPULSIVE", "red"),
    ("PLANNED", "blue"),
    ("RECURRING", "violet"),
    ("SHARED", "cyan"),
    ("REFUNDABLE", "teal"),
    ("EMERGENCY", "rose"),
]


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'fn_categories',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('icon_key', sa.String(length=60), nullable=False),
        sa.Column('color_key', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='ENABLED', nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_fn_categories')),
    )
    with op.batch_alter_table('fn_categories', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fn_categories_id'), ['id'], unique=False)

    op.create_table(
        'fn_payment_methods',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('icon_key', sa.String(length=60), nullable=False),
        sa.Column('color_key', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='ENABLED', nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_fn_payment_methods')),
    )
    with op.batch_alter_table('fn_payment_methods', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fn_payment_methods_id'), ['id'], unique=False)

    op.create_table(
        'fn_user_tags',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('color_key', sa.String(length=30), nullable=False),
        sa.Column('status', sa.String(length=20), server_default='ENABLED', nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_fn_user_tags_user_id_users')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_fn_user_tags')),
        sa.UniqueConstraint('user_id', 'name', name='uq_fn_user_tags_user_id_name'),
    )
    with op.batch_alter_table('fn_user_tags', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fn_user_tags_id'), ['id'], unique=False)

    op.create_table(
        'fn_user_expenses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('amount', sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column('recorded_on', sa.Date(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('payment_method_id', sa.Integer(), nullable=False),
        sa.Column('category_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_fn_user_expenses_user_id_users')),
        sa.ForeignKeyConstraint(
            ['payment_method_id'],
            ['fn_payment_methods.id'],
            name=op.f('fk_fn_user_expenses_payment_method_id_fn_payment_methods'),
        ),
        sa.ForeignKeyConstraint(
            ['category_id'],
            ['fn_categories.id'],
            name=op.f('fk_fn_user_expenses_category_id_fn_categories'),
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_fn_user_expenses')),
    )
    with op.batch_alter_table('fn_user_expenses', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_fn_user_expenses_id'), ['id'], unique=False)
        batch_op.create_index(
            'ix_fn_user_expenses_user_recorded_on', ['user_id', 'recorded_on'], unique=False
        )

    op.create_table(
        'fn_expenses_tags',
        sa.Column('expense_id', sa.Integer(), nullable=False),
        sa.Column('tag_id', sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ['expense_id'], ['fn_user_expenses.id'], name=op.f('fk_fn_expenses_tags_expense_id_fn_user_expenses')
        ),
        sa.ForeignKeyConstraint(
            ['tag_id'], ['fn_user_tags.id'], name=op.f('fk_fn_expenses_tags_tag_id_fn_user_tags')
        ),
        sa.PrimaryKeyConstraint('expense_id', 'tag_id', name=op.f('pk_fn_expenses_tags')),
    )

    # --- Seed de catalogos (sin CRUD todavia) ---
    categories_table = sa.table(
        'fn_categories',
        sa.column('name', sa.String),
        sa.column('icon_key', sa.String),
        sa.column('color_key', sa.String),
        sa.column('status', sa.String),
    )
    op.bulk_insert(
        categories_table,
        [
            {'name': name, 'icon_key': icon_key, 'color_key': color_key, 'status': 'ENABLED'}
            for name, icon_key, color_key in CATEGORIES_SEED
        ],
    )

    payment_methods_table = sa.table(
        'fn_payment_methods',
        sa.column('name', sa.String),
        sa.column('icon_key', sa.String),
        sa.column('color_key', sa.String),
        sa.column('status', sa.String),
    )
    op.bulk_insert(
        payment_methods_table,
        [
            {'name': name, 'icon_key': icon_key, 'color_key': color_key, 'status': 'ENABLED'}
            for name, icon_key, color_key in PAYMENT_METHODS_SEED
        ],
    )

    tags_table = sa.table(
        'fn_user_tags',
        sa.column('user_id', sa.Integer),
        sa.column('name', sa.String),
        sa.column('color_key', sa.String),
        sa.column('status', sa.String),
    )
    op.bulk_insert(
        tags_table,
        [
            {'user_id': 1, 'name': name, 'color_key': color_key, 'status': 'ENABLED'}
            for name, color_key in TAGS_SEED
        ],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('fn_expenses_tags')

    with op.batch_alter_table('fn_user_expenses', schema=None) as batch_op:
        batch_op.drop_index('ix_fn_user_expenses_user_recorded_on')
        batch_op.drop_index(batch_op.f('ix_fn_user_expenses_id'))
    op.drop_table('fn_user_expenses')

    with op.batch_alter_table('fn_user_tags', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_fn_user_tags_id'))
    op.drop_table('fn_user_tags')

    with op.batch_alter_table('fn_payment_methods', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_fn_payment_methods_id'))
    op.drop_table('fn_payment_methods')

    with op.batch_alter_table('fn_categories', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_fn_categories_id'))
    op.drop_table('fn_categories')
