"""Reviewed screenshots on individual report messages and retry-safe replies."""
from alembic import op
import sqlalchemy as sa
revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('report_messages') as batch:
        batch.add_column(sa.Column('request_id', sa.String(36), nullable=True))
        batch.add_column(sa.Column('request_actor', sa.String(), nullable=True))
        batch.add_column(sa.Column('request_fingerprint', sa.String(64), nullable=True))
        batch.create_unique_constraint('uq_report_messages_request_id', ['request_id'])
    op.create_table('message_attachments',
        sa.Column('id', sa.String(), primary_key=True),
        sa.Column('message_id', sa.String(), sa.ForeignKey('report_messages.id'), nullable=False),
        sa.Column('filename', sa.String(150), nullable=False),
        sa.Column('caption', sa.String(500), nullable=False),
        sa.Column('storage_key', sa.String(), nullable=False, unique=True),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('size', sa.Integer(), nullable=False),
        sa.Column('width', sa.Integer(), nullable=False),
        sa.Column('height', sa.Integer(), nullable=False),
        sa.Column('sha256', sa.String(64), nullable=False),
        sa.Column('reviewed_at', sa.String(), nullable=False))
    op.create_index('ix_message_attachments_message_id', 'message_attachments', ['message_id'])


def downgrade():
    op.drop_table('message_attachments')
    with op.batch_alter_table('report_messages') as batch:
        batch.drop_constraint('uq_report_messages_request_id', type_='unique')
        batch.drop_column('request_fingerprint')
        batch.drop_column('request_actor')
        batch.drop_column('request_id')
