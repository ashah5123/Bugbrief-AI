"""Screenshot metadata, clarification history and shared job accounting."""
from alembic import op
import sqlalchemy as sa
revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('ai_jobs', sa.Column('kind', sa.String(), server_default='report', nullable=False))
    op.create_table('attachments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('feedback_id', sa.String(), sa.ForeignKey('feedback.id'), nullable=False),
        sa.Column('filename', sa.String(150), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(), nullable=False),
        sa.Column('reviewed_at', sa.String(), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False),
        sa.Column('analysis', sa.JSON(), nullable=True),
        sa.Column('analyzed_at', sa.String(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('deleted_at', sa.String(), nullable=True))
    op.create_index('ix_attachments_feedback_id', 'attachments', ['feedback_id'])
    op.create_table('clarifications',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('feedback_id', sa.String(), sa.ForeignKey('feedback.id'), nullable=False),
        sa.Column('question', sa.String(500), nullable=False),
        sa.Column('answer', sa.String(2000), nullable=False),
        sa.Column('created_at', sa.String(), nullable=False))
    op.create_index('ix_clarifications_feedback_id', 'clarifications', ['feedback_id'])

def downgrade():
    op.drop_table('clarifications')
    op.drop_table('attachments')
    with op.batch_alter_table('ai_jobs') as batch:
        batch.drop_column('kind')
