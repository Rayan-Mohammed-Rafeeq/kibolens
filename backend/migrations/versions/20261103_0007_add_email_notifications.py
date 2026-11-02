"""add durable incident email notification delivery records"""

from typing import Sequence, Union
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261103_0007"
down_revision: Union[str, None] = "20261102_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "email_notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_key", sa.String(length=128), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider_id", sa.String(length=256), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["incident_id"], ["incidents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_id", "event_key", "recipient", name="uq_email_notification_event_recipient"),
    )
    op.create_index("ix_email_notifications_incident_id", "email_notifications", ["incident_id"])
    op.create_index("ix_email_notifications_status", "email_notifications", ["status"])


def downgrade() -> None:
    op.drop_index("ix_email_notifications_status", table_name="email_notifications")
    op.drop_index("ix_email_notifications_incident_id", table_name="email_notifications")
    op.drop_table("email_notifications")
