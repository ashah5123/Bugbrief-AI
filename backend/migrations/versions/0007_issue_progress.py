"""Independent assignment, issue status and customer-visible progress history."""
from alembic import op
import sqlalchemy as sa

revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('issue_progress',
        sa.Column('feedback_id', sa.String(), sa.ForeignKey('feedback.id'), primary_key=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('assigned_employee_id', sa.String(), sa.ForeignKey('employee_accounts.id'), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.String(), nullable=False))
    op.create_table('issue_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('feedback_id', sa.String(), sa.ForeignKey('feedback.id'), nullable=False),
        sa.Column('label', sa.String(250), nullable=False),
        sa.Column('note', sa.String(1000), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_index('ix_issue_events_feedback_id', 'issue_events', ['feedback_id'])


def downgrade():
    op.drop_table('issue_events')
    op.drop_table('issue_progress')
