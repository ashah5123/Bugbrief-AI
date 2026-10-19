"""Optional structured customer bug-report answers; legacy descriptions stay intact."""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('customer_submissions', sa.Column('guided_details', sa.JSON(), nullable=True))


def downgrade():
    with op.batch_alter_table('customer_submissions') as batch:
        batch.drop_column('guided_details')
