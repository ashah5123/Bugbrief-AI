"""Revocable owner sessions replace legacy signed bearer cookies."""
from alembic import op
import sqlalchemy as sa
revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('owner_sessions',
        sa.Column('token_hash', sa.String(), primary_key=True),
        sa.Column('credential_hash', sa.String(), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False))


def downgrade():
    op.drop_table('owner_sessions')
