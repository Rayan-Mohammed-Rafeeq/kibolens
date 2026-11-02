"""add bounded retry state to incident email notifications"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0009"
down_revision: Union[str, None] = "20261103_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("email_notifications", sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("email_notifications", sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("email_notifications", "attempts", server_default=None)


def downgrade() -> None:
    op.drop_column("email_notifications", "last_attempt_at")
    op.drop_column("email_notifications", "attempts")
