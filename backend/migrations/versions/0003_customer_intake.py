"""Scoped project links and resumable customer submissions."""
from alembic import op
import sqlalchemy as sa
revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('intake_links',sa.Column('id',sa.String(),primary_key=True),sa.Column('project_id',sa.String(),sa.ForeignKey('projects.id'),nullable=False),sa.Column('token',sa.String(),unique=True,nullable=False),sa.Column('created_at',sa.String(),nullable=False),sa.Column('revoked_at',sa.String(),nullable=True))
    op.create_index('ix_intake_links_project_id','intake_links',['project_id'])
    op.create_table('customer_submissions',sa.Column('id',sa.String(),primary_key=True),sa.Column('link_id',sa.String(),sa.ForeignKey('intake_links.id'),nullable=False),sa.Column('feedback_id',sa.String(),sa.ForeignKey('feedback.id'),unique=True,nullable=False),sa.Column('access_token',sa.String(),unique=True,nullable=False),sa.Column('client_nonce',sa.String(),nullable=False),sa.Column('reporter_name',sa.String(80),nullable=False),sa.Column('context',sa.JSON(),nullable=False),sa.Column('stage',sa.String(),nullable=False),sa.Column('processing_started_at',sa.String(),nullable=True),sa.Column('processing_error',sa.String(),nullable=True),sa.Column('consented_at',sa.String(),nullable=True),sa.Column('created_at',sa.String(),nullable=False),sa.Column('submitted_at',sa.String(),nullable=True),sa.UniqueConstraint('link_id','client_nonce'))
    op.create_index('ix_customer_submissions_link_id','customer_submissions',['link_id'])

def downgrade():
    op.drop_table('customer_submissions')
    op.drop_table('intake_links')
