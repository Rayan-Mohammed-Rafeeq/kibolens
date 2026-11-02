"""link conversations to incidents for persistent investigation context"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261102_0005"
down_revision: Union[str, None] = "20261031_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("ix_conversations_incident_id", "conversations", ["incident_id"])
    op.create_foreign_key(
        "fk_conversations_incident_id", "conversations", "incidents",
        ["incident_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_conversations_incident_id", "conversations", type_="foreignkey")
    op.drop_index("ix_conversations_incident_id", table_name="conversations")
    op.drop_column("conversations", "incident_id")
