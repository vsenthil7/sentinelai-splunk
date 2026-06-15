"""tenant_credentials table (BYO / managed integration credentials)

Revision ID: c2d3e4f5a6b7
Revises: b1f2c3d4e5a6
Create Date: 2026-06-15 15:45:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c2d3e4f5a6b7'
down_revision: Union[str, None] = 'b1f2c3d4e5a6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'tenant_credentials',
        sa.Column('tenant_id', sa.String(length=32), nullable=False),
        sa.Column('mode', sa.String(length=20), nullable=False, server_default='managed'),
        sa.Column('splunk_backend', sa.String(length=10), nullable=False, server_default='mock'),
        sa.Column('splunk_host', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('splunk_token_enc', sa.Text(), nullable=False, server_default=''),
        sa.Column('splunk_mcp_url', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('splunk_mcp_token_enc', sa.Text(), nullable=False, server_default=''),
        sa.Column('ai_backend', sa.String(length=10), nullable=False, server_default='mock'),
        sa.Column('ai_model', sa.String(length=120), nullable=False, server_default=''),
        sa.Column('ai_token_enc', sa.Text(), nullable=False, server_default=''),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id'], ),
        sa.PrimaryKeyConstraint('tenant_id'),
    )


def downgrade() -> None:
    op.drop_table('tenant_credentials')
