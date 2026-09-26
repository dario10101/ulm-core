"""agrega name a fn_user_expenses

Revision ID: a271025b8c49
Revises: 31bdd71b624a
Create Date: 2026-09-26 15:40:22.211008

`fn_user_expenses` esta vacia (el modulo se acaba de crear, todavia sin
usuarios reales): a diferencia de 56b5e7da78de_agrega_user_id_a_cl_template_tasks,
no hace falta el patron expandir/rellenar/contraer, se agrega directo como
NOT NULL.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a271025b8c49'
down_revision: Union[str, Sequence[str], None] = '31bdd71b624a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'fn_user_expenses', sa.Column('name', sa.String(length=200), nullable=False)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('fn_user_expenses', 'name')
