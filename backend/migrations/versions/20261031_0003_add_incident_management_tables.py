"""add incident management tables

Revision ID: 20261031_0003
Revises: 20261030_0002
Create Date: 2026-10-31 00:00:00
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20261031_0003"
down_revision = "20261030_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create incident sequence table
    op.create_table(
        "incident_sequences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("next_number", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # Initialize sequence
    op.execute("INSERT INTO incident_sequences (id, next_number) VALUES (1, 1)")

    # Create incidents table
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_number", sa.String(length=32), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("alert_fingerprint", sa.String(length=256), nullable=True),
        sa.Column("affected_host", sa.String(length=256), nullable=True),
        sa.Column("affected_service", sa.String(length=256), nullable=True),
        sa.Column("first_detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "severity IN ('INFO', 'WARNING', 'HIGH', 'CRITICAL')",
            name="ck_incident_severity",
        ),
        sa.CheckConstraint(
            "status IN ('DETECTED', 'INVESTIGATING', 'IDENTIFIED', 'RESOLVING', 'RESOLVED', 'CLOSED')",
            name="ck_incident_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("incident_number"),
    )
    op.create_index("ix_incidents_incident_number", "incidents", ["incident_number"], unique=True)
    op.create_index("ix_incidents_severity", "incidents", ["severity"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_alert_fingerprint", "incidents", ["alert_fingerprint"])
    op.create_index("ix_incidents_affected_service", "incidents", ["affected_service"])
    op.create_index("ix_incidents_first_detected_at", "incidents", ["first_detected_at"])
    op.create_index("ix_incidents_updated_at", "incidents", ["updated_at"])
    op.create_index("ix_incidents_status_severity", "incidents", ["status", "severity"])
    op.create_index(
        "ix_incidents_fingerprint_status", "incidents", ["alert_fingerprint", "status"]
    )

    # Create incident_events table
    op.create_table(
        "incident_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("event_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "event_type IN ('INCIDENT_CREATED', 'ALERT_RECEIVED', 'ALERT_REPEATED', "
            "'STATUS_CHANGED', 'SEVERITY_CHANGED', 'EVIDENCE_CAPTURED', 'INCIDENT_RESOLVED', "
            "'INCIDENT_REOPENED', 'NOTE_ADDED', 'INCIDENT_CLOSED')",
            name="ck_incident_event_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_incident_events_incident_id", "incident_events", ["incident_id"])
    op.create_index("ix_incident_events_created_at", "incident_events", ["created_at"])
    op.create_index(
        "ix_incident_events_incident_created", "incident_events", ["incident_id", "created_at"]
    )

    # Create evidence_records table
    op.create_table(
        "evidence_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_type", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("resource_identifier", sa.String(length=256), nullable=True),
        sa.Column("metric_name", sa.String(length=128), nullable=True),
        sa.Column("metric_value", sa.Numeric(precision=18, scale=6), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "collected_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("evidence_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.CheckConstraint(
            "evidence_type IN ('HOST_METRIC', 'CONTAINER_METRIC', 'CONTAINER_STATE', "
            "'PROMETHEUS_ALERT', 'SYSTEM_EVENT', 'LOG_EXCERPT')",
            name="ck_evidence_type",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_evidence_records_incident_id", "evidence_records", ["incident_id"])
    op.create_index("ix_evidence_records_evidence_type", "evidence_records", ["evidence_type"])
    op.create_index(
        "ix_evidence_records_incident_type", "evidence_records", ["incident_id", "evidence_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_records_incident_type", table_name="evidence_records")
    op.drop_index("ix_evidence_records_evidence_type", table_name="evidence_records")
    op.drop_index("ix_evidence_records_incident_id", table_name="evidence_records")
    op.drop_table("evidence_records")

    op.drop_index("ix_incident_events_incident_created", table_name="incident_events")
    op.drop_index("ix_incident_events_created_at", table_name="incident_events")
    op.drop_index("ix_incident_events_incident_id", table_name="incident_events")
    op.drop_table("incident_events")

    op.drop_index("ix_incidents_fingerprint_status", table_name="incidents")
    op.drop_index("ix_incidents_status_severity", table_name="incidents")
    op.drop_index("ix_incidents_updated_at", table_name="incidents")
    op.drop_index("ix_incidents_first_detected_at", table_name="incidents")
    op.drop_index("ix_incidents_affected_service", table_name="incidents")
    op.drop_index("ix_incidents_alert_fingerprint", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_severity", table_name="incidents")
    op.drop_index("ix_incidents_incident_number", table_name="incidents")
    op.drop_table("incidents")

    op.drop_table("incident_sequences")
