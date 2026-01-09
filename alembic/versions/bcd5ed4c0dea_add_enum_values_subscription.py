"""add_enum_values_subscription

Revision ID: bcd5ed4c0dea
Revises: b06eac30f410
Create Date: 2025-12-26 10:37:34.288061

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bcd5ed4c0dea'
down_revision: Union[str, None] = 'b06eac30f410'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres doesn't support ALTER TYPE in transaction block for ADD VALUE
    
    op.execute("COMMIT")
    op.execute("ALTER TYPE consumersubscriptionstatus ADD VALUE 'PENDING_PAYMENT'")
    op.execute("ALTER TYPE consumersubscriptionstatus ADD VALUE 'PENDING_REVIEW'")
    op.execute("ALTER TYPE consumersubscriptionstatus ADD VALUE 'REJECTED'")


def downgrade() -> None:
    pass
