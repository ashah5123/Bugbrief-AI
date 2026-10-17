"""Company priorities and calendar due dates for issue triage."""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('issue_progress', sa.Column('priority', sa.String(), nullable=False, server_default='normal'))
    op.add_column('issue_progress', sa.Column('due_date', sa.String(10), nullable=True))


def downgrade():
    op.drop_column('issue_progress', 'due_date')
    op.drop_column('issue_progress', 'priority')
