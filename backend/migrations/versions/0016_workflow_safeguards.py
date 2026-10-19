"""Draft conflicts, independent archives and employee project capabilities."""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customer_submissions', sa.Column('draft_version', sa.Integer(), nullable=False, server_default='1'))
    op.add_column('customer_submissions', sa.Column('archived_at', sa.String(), nullable=True))
    op.add_column('feedback', sa.Column('archived_at', sa.String(), nullable=True))
    op.add_column('employee_projects', sa.Column('role', sa.String(), nullable=False, server_default='contributor'))
    op.add_column('employee_projects', sa.Column('can_delete', sa.Integer(), nullable=False, server_default='0'))


def downgrade():
    for table, columns in [('employee_projects', ['can_delete', 'role']), ('feedback', ['archived_at']),
                           ('customer_submissions', ['archived_at', 'draft_version'])]:
        with op.batch_alter_table(table) as batch:
            for column in columns:
                batch.drop_column(column)
