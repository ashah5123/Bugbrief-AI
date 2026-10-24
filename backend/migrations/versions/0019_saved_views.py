"""Private, versioned company inbox views."""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('saved_views',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('scope', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('slot', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('name_key', sa.String(240), nullable=False),
        sa.Column('filters', sa.JSON(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('scope', 'account_id', 'name_key', name='uq_saved_view_name'),
        sa.UniqueConstraint('scope', 'account_id', 'slot', name='uq_saved_view_slot'))


def downgrade():
    op.drop_table('saved_views')
