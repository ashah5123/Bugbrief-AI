"""Report conversation, verified accounts and one-use account actions."""
from alembic import op
import sqlalchemy as sa
revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('customer_accounts', 'employee_accounts'):
        op.add_column(table, sa.Column('email_verified_at', sa.String(), nullable=True))
    op.add_column('employee_accounts', sa.Column('disabled_at', sa.String(), nullable=True))
    op.create_table('report_messages',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('feedback_id', sa.String(), sa.ForeignKey('feedback.id'), nullable=False),
        sa.Column('visibility', sa.String(), nullable=False),
        sa.Column('author_role', sa.String(), nullable=False),
        sa.Column('author_name', sa.String(80), nullable=False),
        sa.Column('body', sa.String(4000), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_index('ix_report_messages_feedback_id', 'report_messages', ['feedback_id'])
    op.create_table('account_actions',
        sa.Column('token_hash', sa.String(), primary_key=True),
        sa.Column('scope', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('email', sa.String(254), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False),
        sa.Column('used_at', sa.String(), nullable=True),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_table('mail_messages',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('recipient', sa.String(254), nullable=False),
        sa.Column('subject', sa.String(200), nullable=False),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('delivery', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))


def downgrade():
    for table in ('mail_messages', 'account_actions', 'report_messages'):
        op.drop_table(table)
    op.drop_column('employee_accounts', 'disabled_at')
    for table in ('customer_accounts', 'employee_accounts'):
        op.drop_column(table, 'email_verified_at')
