"""Customer-facing project team names."""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('team_name', sa.String(100), nullable=False, server_default=''))


def downgrade():
    op.drop_column('projects', 'team_name')
