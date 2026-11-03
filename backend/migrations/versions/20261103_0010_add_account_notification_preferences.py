"""add account email verification and incident notification preferences"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261103_0010"
down_revision: Union[str, None] = "20261103_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("incident_notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("incident_notification_min_severity", sa.String(length=16), nullable=False, server_default="WARNING"),
    )
    op.add_column(
        "users",
        sa.Column("recovery_notifications_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    # Existing accounts have already completed OTP authentication in the
    # deployed application. Preserve their ability to receive alerts while
    # requiring OTP verification for newly provisioned accounts.
    op.execute(sa.text("UPDATE users SET email_verified_at = created_at WHERE email IS NOT NULL"))
    op.alter_column("users", "incident_notifications_enabled", server_default=None)
    op.alter_column("users", "incident_notification_min_severity", server_default=None)
    op.alter_column("users", "recovery_notifications_enabled", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "recovery_notifications_enabled")
    op.drop_column("users", "incident_notification_min_severity")
    op.drop_column("users", "incident_notifications_enabled")
    op.drop_column("users", "email_verified_at")
