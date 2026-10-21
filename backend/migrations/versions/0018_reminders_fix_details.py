"""Durable reminder receipts, workspace policy and customer retest instructions."""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('issue_progress', sa.Column('fix_details', sa.JSON(), nullable=True))
    op.add_column('issue_progress', sa.Column('retest_requested_at', sa.String(), nullable=True))
    # Additive changes avoid rebuilding a table referenced by existing outbox messages.
    op.add_column('notifications', sa.Column('reminder_key', sa.String(64), nullable=True))
    op.add_column('notifications', sa.Column('reminder_episode', sa.String(), nullable=True))
    op.create_index('uq_notification_reminder_key', 'notifications', ['reminder_key'], unique=True)
    op.create_table('reminder_policy',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('enabled', sa.Integer(), nullable=False),
        sa.Column('reply_hours', sa.Integer(), nullable=False),
        sa.Column('retest_hours', sa.Integer(), nullable=False),
        sa.Column('timezone', sa.String(100), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False))


def downgrade():
    op.drop_table('reminder_policy')
    op.drop_index('uq_notification_reminder_key', table_name='notifications')
    op.drop_column('notifications', 'reminder_episode')
    op.drop_column('notifications', 'reminder_key')
    op.drop_column('issue_progress', 'retest_requested_at')
    op.drop_column('issue_progress', 'fix_details')
