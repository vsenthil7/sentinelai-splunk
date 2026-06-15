"""tenant saas fields: status, plan, trial_ends_at, settings

Revision ID: b1f2c3d4e5a6
Revises: cace9457d0b0
Create Date: 2026-06-15 14:20:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b1f2c3d4e5a6'
down_revision: Union[str, None] = 'cace9457d0b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('status', sa.String(length=20), nullable=False, server_default='active')
        )
        batch_op.add_column(
            sa.Column('plan', sa.String(length=20), nullable=False, server_default='enterprise')
        )
        batch_op.add_column(
            sa.Column('trial_ends_at', sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column('settings', sa.JSON(), nullable=False, server_default='{}')
        )
        batch_op.create_index(batch_op.f('ix_tenants_status'), ['status'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('tenants', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_tenants_status'))
        batch_op.drop_column('settings')
        batch_op.drop_column('trial_ends_at')
        batch_op.drop_column('plan')
        batch_op.drop_column('status')
