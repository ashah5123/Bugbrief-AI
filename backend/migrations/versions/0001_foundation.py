"""Phase 1 projects, feedback, report data and persistent AI attempt accounting."""
from alembic import op
import sqlalchemy as sa
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('projects', sa.Column('id', sa.String(), primary_key=True), sa.Column('name', sa.String(100), nullable=False), sa.Column('url', sa.String(2000), nullable=False), sa.Column('created_at', sa.String(), nullable=False))
    op.create_table('feedback', sa.Column('id', sa.String(), primary_key=True), sa.Column('project_id', sa.String(), sa.ForeignKey('projects.id'), nullable=False), sa.Column('text', sa.Text(), nullable=False), sa.Column('page_url', sa.String(2000), nullable=False), sa.Column('device', sa.String(200), nullable=False), sa.Column('browser', sa.String(200), nullable=False), sa.Column('status', sa.String(), nullable=False), sa.Column('report', sa.JSON(), nullable=True), sa.Column('proposal', sa.JSON(), nullable=True), sa.Column('version', sa.Integer(), nullable=False), sa.Column('error', sa.Text(), nullable=True), sa.Column('created_at', sa.String(), nullable=False), sa.Column('updated_at', sa.String(), nullable=False))
    op.create_table('ai_jobs', sa.Column('id', sa.String(), primary_key=True), sa.Column('feedback_id', sa.String(), sa.ForeignKey('feedback.id'), nullable=False), sa.Column('day', sa.String(), nullable=False), sa.Column('outcome', sa.String(), nullable=False), sa.Column('latency_ms', sa.Float(), nullable=False), sa.Column('input_tokens', sa.Integer(), nullable=False), sa.Column('output_tokens', sa.Integer(), nullable=False), sa.Column('model', sa.String(), nullable=False))
    op.create_index('ix_ai_jobs_day', 'ai_jobs', ['day'])

def downgrade():
    op.drop_table('ai_jobs')
    op.drop_table('feedback')
    op.drop_table('projects')
