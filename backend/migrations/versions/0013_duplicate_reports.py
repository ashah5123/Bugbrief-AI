"""Flat duplicate groups and retry-safe shared updates."""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('duplicate_groups',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('work_status', sa.String(), nullable=False, server_default='new'),
        sa.Column('assigned_employee_id', sa.String(), sa.ForeignKey('employee_accounts.id'), nullable=True),
        sa.Column('main_feedback_id', sa.String(), sa.ForeignKey('feedback.id'), nullable=False, unique=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_table('duplicate_members',
        sa.Column('feedback_id', sa.String(), sa.ForeignKey('feedback.id'), primary_key=True),
        sa.Column('group_id', sa.String(), sa.ForeignKey('duplicate_groups.id'), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_index('ix_duplicate_members_group_id', 'duplicate_members', ['group_id'])
    op.create_table('duplicate_actions',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('group_id', sa.String(), sa.ForeignKey('duplicate_groups.id'), nullable=False),
        sa.Column('fingerprint', sa.String(64), nullable=False),
        sa.Column('count', sa.Integer(), nullable=False))
    op.create_index('ix_duplicate_actions_group_id', 'duplicate_actions', ['group_id'])


def downgrade():
    op.drop_table('duplicate_actions')
    op.drop_table('duplicate_members')
    op.drop_table('duplicate_groups')
