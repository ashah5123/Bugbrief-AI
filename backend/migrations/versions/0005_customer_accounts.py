"""Customer accounts, revocable sessions and project invitations."""
from alembic import op
import sqlalchemy as sa

revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('customer_accounts',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('email', sa.String(254), unique=True, nullable=False),
        sa.Column('name', sa.String(80), nullable=False),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_table('customer_sessions',
        sa.Column('token_hash', sa.String(), primary_key=True),
        sa.Column('account_id', sa.String(), sa.ForeignKey('customer_accounts.id'), nullable=False),
        sa.Column('expires_at', sa.Float(), nullable=False))
    op.create_index('ix_customer_sessions_account_id', 'customer_sessions', ['account_id'])
    op.create_table('customer_memberships',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('account_id', sa.String(), sa.ForeignKey('customer_accounts.id'), nullable=False),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('link_id', sa.String(), sa.ForeignKey('intake_links.id'), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.UniqueConstraint('account_id', 'project_id'))
    op.create_index('ix_customer_memberships_account_id', 'customer_memberships', ['account_id'])
    with op.batch_alter_table('customer_submissions') as batch:
        batch.add_column(sa.Column('account_id', sa.String(), nullable=True))
        batch.create_foreign_key('fk_customer_submission_account', 'customer_accounts', ['account_id'], ['id'])
        batch.create_index('ix_customer_submissions_account_id', ['account_id'])


def downgrade():
    with op.batch_alter_table('customer_submissions') as batch:
        batch.drop_index('ix_customer_submissions_account_id')
        batch.drop_constraint('fk_customer_submission_account', type_='foreignkey')
        batch.drop_column('account_id')
    op.drop_table('customer_memberships')
    op.drop_table('customer_sessions')
    op.drop_table('customer_accounts')
