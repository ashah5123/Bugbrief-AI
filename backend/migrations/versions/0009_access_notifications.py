"""Project membership and per-account notifications with optional email."""
from alembic import op
import sqlalchemy as sa
revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('projects', sa.Column('customer_access', sa.String(), nullable=False, server_default='link'))
    op.add_column('customer_memberships', sa.Column('revoked_at', sa.String(), nullable=True))
    op.create_table('employee_projects',
        sa.Column('employee_id', sa.String(), sa.ForeignKey('employee_accounts.id'), primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), primary_key=True),
        sa.Column('created_at', sa.String(), nullable=False))
    # Preserve access held by existing employees. New employees get only explicitly assigned projects.
    op.execute("INSERT INTO employee_projects (employee_id, project_id, created_at) SELECT e.id, p.id, e.created_at FROM employee_accounts e CROSS JOIN projects p WHERE e.disabled_at IS NULL")
    op.create_table('notification_preferences',
        sa.Column('scope', sa.String(), primary_key=True),
        sa.Column('account_id', sa.String(), primary_key=True),
        sa.Column('email_enabled', sa.Integer(), nullable=False))
    op.create_table('notifications',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('scope', sa.String(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('feedback_id', sa.String(), sa.ForeignKey('feedback.id'), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('read_at', sa.String(), nullable=True))
    for column in ('scope', 'account_id', 'feedback_id'):
        op.create_index('ix_notifications_' + column, 'notifications', [column])
    with op.batch_alter_table('mail_messages') as batch:
        batch.add_column(sa.Column('notification_id', sa.String(), nullable=True))
        batch.create_foreign_key('fk_mail_notification', 'notifications', ['notification_id'], ['id'])


def downgrade():
    with op.batch_alter_table('mail_messages') as batch:
        batch.drop_constraint('fk_mail_notification', type_='foreignkey')
        batch.drop_column('notification_id')
    for table in ('notifications', 'notification_preferences', 'employee_projects'):
        op.drop_table(table)
    op.drop_column('customer_memberships', 'revoked_at')
    op.drop_column('projects', 'customer_access')
