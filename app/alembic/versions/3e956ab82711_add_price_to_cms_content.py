"""add_price_to_cms_content

Revision ID: 3e956ab82711
Revises: e6918ac93400
Create Date: 2026-01-09 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3e956ab82711'
down_revision: Union[str, None] = 'e6918ac93400'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('cms_content', sa.Column('price', sa.Float(), nullable=True, server_default='0.0'))


def downgrade() -> None:
    op.drop_column('cms_content', 'price')
