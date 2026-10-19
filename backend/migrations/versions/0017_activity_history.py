"""Attributed, visibility-scoped report history and owner-only project access history."""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('issue_events', sa.Column('actor_name', sa.String(80), nullable=True))
    op.add_column('issue_events', sa.Column('actor_role', sa.String(), nullable=True))
    op.add_column('issue_events', sa.Column('visibility', sa.String(), nullable=False, server_default='public'))
    op.create_table('project_events',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False),
        sa.Column('actor_name', sa.String(80), nullable=True),
        sa.Column('actor_role', sa.String(), nullable=True),
        sa.Column('label', sa.String(200), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_index('ix_project_events_project_id', 'project_events', ['project_id'])


def downgrade():
    op.drop_table('project_events')
    with op.batch_alter_table('issue_events') as batch:
        batch.drop_column('visibility')
        batch.drop_column('actor_role')
        batch.drop_column('actor_name')
