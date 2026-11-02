"""add stable logical incident recurrence fingerprint"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0008"
down_revision: Union[str, None] = "20261103_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("incidents", sa.Column("logical_fingerprint", sa.String(length=64), nullable=True))
    op.create_index("ix_incidents_logical_fingerprint", "incidents", ["logical_fingerprint"])
    op.create_index("ix_incidents_logical_fingerprint_status", "incidents", ["logical_fingerprint", "status"])


def downgrade() -> None:
    op.drop_index("ix_incidents_logical_fingerprint_status", table_name="incidents")
    op.drop_index("ix_incidents_logical_fingerprint", table_name="incidents")
    op.drop_column("incidents", "logical_fingerprint")
