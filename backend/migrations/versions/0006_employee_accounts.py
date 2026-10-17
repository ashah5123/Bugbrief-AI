"""Named company employees and revocable workspace sessions."""
from alembic import op
import sqlalchemy as sa

revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('employee_accounts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('email', sa.String(254), unique=True, nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_table('employee_sessions',
        sa.Column('token_hash', sa.String(), primary_key=True),
        sa.Column('account_id', sa.String(), sa.ForeignKey('employee_accounts.id'), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False))
    op.create_index('ix_employee_sessions_account_id', 'employee_sessions', ['account_id'])


def downgrade():
    op.drop_table('employee_sessions')
    op.drop_table('employee_accounts')
