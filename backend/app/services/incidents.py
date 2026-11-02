import logging
from datetime import datetime, timedelta
from datetime import timezone as tz
from typing import Literal
from uuid import UUID

UTC = tz.utc

from sqlalchemy import and_, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.incident import (
    EvidenceRecord,
    Incident,
    IncidentEvent,
    IncidentSequence,
    IncidentSeverity,
    IncidentStatus,
)
from app.monitoring.service import MonitoringService
from app.schemas.monitoring import AlertmanagerAlert
from app.monitoring.alert_fingerprint import logical_alert_fingerprint

logger = logging.getLogger(__name__)

# Valid state transitions
VALID_TRANSITIONS: dict[IncidentStatus, list[IncidentStatus]] = {
    "DETECTED": ["INVESTIGATING", "RESOLVED"],
    "INVESTIGATING": ["IDENTIFIED", "DETECTED", "RESOLVED"],
    "IDENTIFIED": ["RESOLVING", "INVESTIGATING", "RESOLVED"],
    "RESOLVING": ["RESOLVED", "IDENTIFIED"],
    "RESOLVED": ["CLOSED", "INVESTIGATING"],  # Allow reopening
    "CLOSED": [],  # Terminal state
}


class IncidentService:
    """
    Incident management business logic.

    Handles incident lifecycle, alert correlation, event recording, and evidence collection.
    """

    def __init__(self, db: Session, monitoring_service: MonitoringService | None = None):
        self.db = db
        self.monitoring_service = monitoring_service

    def _generate_incident_number(self) -> str:
        """
        Generate unique incident reference using database sequence.

        Thread-safe and handles concurrent requests via row-level locking.
        """
        # Get or create sequence record with lock
        stmt = (
            select(IncidentSequence)
            .where(IncidentSequence.id == 1)
            .with_for_update(skip_locked=False)
        )
        sequence = self.db.execute(stmt).scalar_one_or_none()

        if sequence is None:
            sequence = IncidentSequence(id=1, next_number=1)
            self.db.add(sequence)
            self.db.flush()

        incident_number = f"INC-{sequence.next_number:06d}"
        sequence.next_number += 1
        self.db.flush()

        return incident_number

    def create_incident(
        self,
        title: str,
        description: str,
        severity: IncidentSeverity,
        source: str = "alertmanager",
        alert_fingerprint: str | None = None,
        logical_fingerprint: str | None = None,
        affected_host: str | None = None,
        affected_service: str | None = None,
        first_detected_at: datetime | None = None,
    ) -> Incident:
        """Create a new incident and record creation event."""
        now = datetime.now(UTC)
        first_detected = first_detected_at or now

        incident_number = self._generate_incident_number()

        incident = Incident(
            incident_number=incident_number,
            title=title,
            description=description,
            severity=severity,
            status="DETECTED",
            source=source,
            alert_fingerprint=alert_fingerprint,
            logical_fingerprint=logical_fingerprint,
            affected_host=affected_host,
            affected_service=affected_service,
            first_detected_at=first_detected,
            last_observed_at=now,
        )
        self.db.add(incident)
        self.db.flush()

        # Record creation event
        self.record_incident_event(
            incident_id=incident.id,
            event_type="INCIDENT_CREATED",
            description=f"Incident {incident_number} created: {title}",
            new_status="DETECTED",
            source=source,
            metadata={
                "severity": severity,
                "alert_fingerprint": alert_fingerprint,
                "logical_fingerprint": logical_fingerprint,
                "affected_service": affected_service,
            },
        )

        return incident

    def get_incident(self, incident_id: UUID) -> Incident | None:
        """Retrieve incident by ID."""
        return self.db.execute(
            select(Incident).where(Incident.id == incident_id)
        ).scalar_one_or_none()

    def get_incident_by_number(self, incident_number: str) -> Incident | None:
        """Retrieve incident by human-readable number."""
        return self.db.execute(
            select(Incident).where(Incident.incident_number == incident_number)
        ).scalar_one_or_none()

    def list_incidents(
        self,
        page: int = 1,
        page_size: int = 50,
        severity: IncidentSeverity | None = None,
        status: IncidentStatus | None = None,
        affected_service: str | None = None,
        search: str | None = None,
    ) -> tuple[list[Incident], int]:
        """
        List incidents with filtering and pagination.

        Returns (incidents, total_count).
        """
        query = select(Incident)

        # Apply filters
        conditions = []
        if severity:
            conditions.append(Incident.severity == severity)
        if status:
            conditions.append(Incident.status == status)
        if affected_service:
            conditions.append(Incident.affected_service == affected_service)
        if search:
            search_pattern = f"%{search}%"
            conditions.append(
                or_(
                    Incident.incident_number.ilike(search_pattern),
                    Incident.title.ilike(search_pattern),
                    Incident.description.ilike(search_pattern),
                )
            )

        if conditions:
            query = query.where(and_(*conditions))

        # Get total count
        count_query = select(func.count()).select_from(query.subquery())
        total = self.db.execute(count_query).scalar_one()

        # Apply pagination and ordering
        query = query.order_by(desc(Incident.updated_at)).offset((page - 1) * page_size).limit(page_size)

        incidents = list(self.db.execute(query).scalars().all())
        return incidents, total

    def update_incident_status(
        self, incident_id: UUID, new_status: IncidentStatus, note: str | None = None, source: str = "user"
    ) -> Incident:
        """
        Update incident status with validation and event recording.

        Raises ValueError if transition is invalid.
        """
        incident = self.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        previous_status: IncidentStatus = incident.status  # type: ignore

        # Validate transition
        if new_status not in VALID_TRANSITIONS.get(previous_status, []):
            raise ValueError(
                f"Invalid status transition from {previous_status} to {new_status}"
            )

        incident.status = new_status
        incident.updated_at = datetime.now(UTC)

        # Handle resolution
        if new_status == "RESOLVED" and not incident.resolved_at:
            incident.resolved_at = datetime.now(UTC)

        # Handle reopening
        if previous_status == "RESOLVED" and new_status == "INVESTIGATING":
            incident.resolved_at = None

        description = f"Status changed from {previous_status} to {new_status}"
        if note:
            description += f": {note}"

        event_type = "STATUS_CHANGED"
        if new_status == "RESOLVED":
            event_type = "INCIDENT_RESOLVED"
        elif previous_status == "RESOLVED":
            event_type = "INCIDENT_REOPENED"
        elif new_status == "CLOSED":
            event_type = "INCIDENT_CLOSED"

        self.record_incident_event(
            incident_id=incident.id,
            event_type=event_type,
            description=description,
            previous_status=previous_status,
            new_status=new_status,
            source=source,
            metadata={"note": note} if note else None,
        )

        self.db.flush()
        return incident

    def update_incident_severity(
        self, incident_id: UUID, new_severity: IncidentSeverity, note: str | None = None, source: str = "user"
    ) -> Incident:
        """Update incident severity and record change."""
        incident = self.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        previous_severity = incident.severity
        incident.severity = new_severity
        incident.updated_at = datetime.now(UTC)

        description = f"Severity changed from {previous_severity} to {new_severity}"
        if note:
            description += f": {note}"

        self.record_incident_event(
            incident_id=incident.id,
            event_type="SEVERITY_CHANGED",
            description=description,
            source=source,
            metadata={
                "previous_severity": previous_severity,
                "new_severity": new_severity,
                "note": note,
            },
        )

        self.db.flush()
        return incident

    def resolve_incident(
        self, incident_id: UUID, note: str | None = None, source: str = "user"
    ) -> Incident:
        """Convenience method to resolve incident."""
        return self.update_incident_status(incident_id, "RESOLVED", note=note, source=source)

    def close_incident(
        self, incident_id: UUID, note: str | None = None, source: str = "user"
    ) -> Incident:
        """Convenience method to close incident."""
        return self.update_incident_status(incident_id, "CLOSED", note=note, source=source)

    def reopen_incident(
        self, incident_id: UUID, note: str | None = None, source: str = "alertmanager"
    ) -> Incident:
        """Reopen a resolved incident when recurrence detected."""
        incident = self.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        if incident.status != "RESOLVED":
            raise ValueError(f"Can only reopen RESOLVED incidents, current status: {incident.status}")

        return self.update_incident_status(incident_id, "INVESTIGATING", note=note, source=source)

    def add_note(
        self, incident_id: UUID, note: str, source: str = "user"
    ) -> IncidentEvent:
        """Add a note to incident timeline."""
        incident = self.get_incident(incident_id)
        if not incident:
            raise ValueError(f"Incident {incident_id} not found")

        incident.updated_at = datetime.now(UTC)
        self.db.flush()

        return self.record_incident_event(
            incident_id=incident_id,
            event_type="NOTE_ADDED",
            description=note,
            source=source,
        )

    def record_incident_event(
        self,
        incident_id: UUID,
        event_type: str,
        description: str,
        previous_status: str | None = None,
        new_status: str | None = None,
        source: str = "system",
        metadata: dict | None = None,
    ) -> IncidentEvent:
        """Record an event in incident timeline."""
        event = IncidentEvent(
            incident_id=incident_id,
            event_type=event_type,
            description=description,
            previous_status=previous_status,
            new_status=new_status,
            source=source,
            event_metadata=metadata,
        )
        self.db.add(event)
        self.db.flush()
        return event

    def get_incident_timeline(self, incident_id: UUID) -> list[IncidentEvent]:
        """Retrieve incident event timeline in chronological order."""
        return list(
            self.db.execute(
                select(IncidentEvent)
                .where(IncidentEvent.incident_id == incident_id)
                .order_by(IncidentEvent.created_at)
            )
            .scalars()
            .all()
        )

    def capture_evidence(
        self,
        incident_id: UUID,
        evidence_type: str,
        source: str = "prometheus",
        resource_identifier: str | None = None,
        metric_name: str | None = None,
        metric_value: float | None = None,
        unit: str | None = None,
        observed_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> EvidenceRecord:
        """Record evidence for incident."""
        evidence = EvidenceRecord(
            incident_id=incident_id,
            evidence_type=evidence_type,
            source=source,
            resource_identifier=resource_identifier,
            metric_name=metric_name,
            metric_value=metric_value,
            unit=unit,
            observed_at=observed_at,
            evidence_metadata=metadata,
        )
        self.db.add(evidence)
        self.db.flush()
        return evidence

    def get_incident_evidence(self, incident_id: UUID) -> list[EvidenceRecord]:
        """Retrieve all evidence for an incident."""
        return list(
            self.db.execute(
                select(EvidenceRecord)
                .where(EvidenceRecord.incident_id == incident_id)
                .order_by(EvidenceRecord.collected_at)
            )
            .scalars()
            .all()
        )

    def process_alert(self, alert: AlertmanagerAlert) -> Incident:
        """
        Process an Alertmanager webhook alert.

        Creates new incident or updates existing one based on fingerprint.
        Handles both firing and resolved alerts idempotently.
        """
        fingerprint = alert.fingerprint
        now = datetime.now(UTC)
        if alert.labels.get("kibolens_simulated") == "true":
            alert_source = "simulation"
        elif alert.labels.get("kibolens_lab") == "true":
            alert_source = "docker_lab"
        elif alert.labels.get("kibolens_source") == "docker":
            alert_source = "docker"
        else:
            alert_source = "alertmanager"

        # Extract alert information. The external fingerprint remains the
        # exact source identity; the logical fingerprint correlates equivalent
        # alerts whose source fingerprint changed during re-delivery.
        title = alert.annotations.get("summary", alert.labels.get("alertname", "Unknown Alert"))
        description = alert.annotations.get(
            "description", alert.annotations.get("message", "No description provided")
        )
        severity = self._map_alert_severity(alert.labels.get("severity", "warning"))
        affected_service = alert.labels.get("job", alert.labels.get("service"))
        affected_host = alert.labels.get("instance", alert.labels.get("node"))
        logical_fingerprint = logical_alert_fingerprint(
            alert_source,
            alert.labels.get("alertname", title),
            affected_host or affected_service or "",
        )

        # Find existing active incident with this fingerprint
        existing = self.db.execute(
            select(Incident)
            .where(
                and_(
                    or_(
                        Incident.alert_fingerprint == fingerprint,
                        and_(logical_fingerprint is not None, Incident.logical_fingerprint == logical_fingerprint),
                    ),
                    Incident.status.in_(["DETECTED", "INVESTIGATING", "IDENTIFIED", "RESOLVING"]),
                )
            )
        ).scalar_one_or_none()

        if alert.status == "firing":
            if existing:
                # Update existing incident
                last_observed = existing.last_observed_at
                if last_observed.tzinfo is None:
                    last_observed = last_observed.replace(tzinfo=UTC)
                if now <= last_observed:
                    now = last_observed + timedelta(microseconds=1)
                existing.last_observed_at = now
                existing.updated_at = now

                # Update severity if changed
                if existing.severity != severity:
                    old_severity = existing.severity
                    existing.severity = severity
                    self.record_incident_event(
                        incident_id=existing.id,
                        event_type="SEVERITY_CHANGED",
                        description=f"Alert severity changed from {old_severity} to {severity}",
                        source=alert_source,
                        metadata={"previous_severity": old_severity, "new_severity": severity},
                    )

                self.record_incident_event(
                    incident_id=existing.id,
                    event_type="ALERT_REPEATED",
                    description=f"Alert repeated: {title}",
                    source=alert_source,
                    metadata={"labels": alert.labels, "annotations": alert.annotations},
                )

                incident = existing
            else:
                # Check for recently resolved incident (recurrence)
                recently_resolved = self.db.execute(
                    select(Incident)
                    .where(
                        and_(
                            or_(
                                Incident.alert_fingerprint == fingerprint,
                                and_(logical_fingerprint is not None, Incident.logical_fingerprint == logical_fingerprint),
                            ),
                            Incident.status == "RESOLVED",
                        )
                    )
                    .order_by(desc(Incident.resolved_at))
                    .limit(1)
                ).scalar_one_or_none()

                if recently_resolved:
                    # Reopen the incident
                    incident = self.reopen_incident(
                        recently_resolved.id,
                        note="Alert fired again after resolution",
                        source=alert_source,
                    )
                    incident.last_observed_at = now

                    self.record_incident_event(
                        incident_id=incident.id,
                        event_type="ALERT_RECEIVED",
                        description=f"Recurrent alert: {title}",
                        source=alert_source,
                        metadata={"labels": alert.labels, "annotations": alert.annotations},
                    )
                else:
                    # Create new incident
                    incident = self.create_incident(
                        title=title,
                        description=description,
                        severity=severity,
                        source=alert_source,
                        alert_fingerprint=fingerprint,
                        logical_fingerprint=logical_fingerprint,
                        affected_host=affected_host,
                        affected_service=affected_service,
                        first_detected_at=now,
                    )

                    self.record_incident_event(
                        incident_id=incident.id,
                        event_type="ALERT_RECEIVED",
                        description=f"Alert received: {title}",
                        source=alert_source,
                        metadata={"labels": alert.labels, "annotations": alert.annotations},
                    )

            # Collect evidence if monitoring service is available
            if self.monitoring_service:
                self._collect_incident_evidence(incident)

        else:  # resolved
            if existing:
                # Resolve the incident
                try:
                    self.resolve_incident(
                        existing.id,
                        note="Alert resolved by Alertmanager",
                        source=alert_source,
                    )
                except ValueError:
                    # Already resolved or invalid transition
                    pass

                incident = existing
            else:
                # Resolved alert for unknown incident - log and ignore
                logger.info(f"Received resolved alert for unknown fingerprint: {fingerprint}")
                # Create a minimal incident record for audit trail
                incident = self.create_incident(
                    title=title,
                    description=f"Resolved alert (no prior firing alert recorded): {description}",
                    severity=severity,
                    source=alert_source,
                    alert_fingerprint=fingerprint,
                    logical_fingerprint=logical_fingerprint,
                    affected_host=affected_host,
                    affected_service=affected_service,
                    first_detected_at=now,
                )
                self.resolve_incident(
                    incident.id,
                    note="Alert was already resolved when first seen",
                    source=alert_source,
                )

        self.db.flush()
        return incident

    def _map_alert_severity(self, severity_label: str) -> IncidentSeverity:
        """Map Alertmanager severity labels to incident severity."""
        severity_map = {
            "critical": "CRITICAL",
            "high": "HIGH",
            "warning": "WARNING",
            "info": "INFO",
        }
        return severity_map.get(severity_label.lower(), "WARNING")  # type: ignore

    def _collect_incident_evidence(self, incident: Incident) -> None:
        """
        Collect available telemetry evidence for an incident.

        Fails gracefully if evidence collection is unavailable.
        """
        if not self.monitoring_service:
            return

        try:
            # Capture alert evidence
            self.capture_evidence(
                incident_id=incident.id,
                evidence_type="PROMETHEUS_ALERT",
                source="alertmanager",
                resource_identifier=incident.affected_service or "unknown",
                metadata={
                    "fingerprint": incident.alert_fingerprint,
                    "severity": incident.severity,
                    "title": incident.title,
                },
            )

            # Prometheus and Docker collection are asynchronous. The webhook
            # awaits collect_incident_evidence() after alert correlation.

        except Exception as e:
            logger.error(f"Evidence collection failed for incident {incident.id}: {e}")
            # Record the failure but don't block incident creation
            self.record_incident_event(
                incident_id=incident.id,
                event_type="EVIDENCE_CAPTURED",
                description=f"Evidence collection failed: {str(e)}",
                source="system",
                metadata={"error": str(e), "success": False},
            )

    async def collect_incident_evidence(self, incident: Incident) -> None:
        """Collect live Prometheus and Docker evidence after alert ingestion."""
        if not self.monitoring_service:
            return
        try:
            summary_result = await self.monitoring_service.summary()
            if summary_result.monitoring_available:
                for metric in summary_result.metrics:
                    if metric.value is not None and metric.availability == "available":
                        self.capture_evidence(
                            incident_id=incident.id, evidence_type="HOST_METRIC",
                            source="prometheus", metric_name=metric.name,
                            metric_value=metric.value, unit=metric.unit,
                            observed_at=metric.observation_at,
                        )
            if incident.affected_service:
                containers = await self.monitoring_service.containers()
                for container in containers:
                    if container.availability == "available" and (
                        container.name == incident.affected_service
                        or incident.affected_service in container.name
                    ):
                        self.capture_evidence(
                            incident_id=incident.id, evidence_type="CONTAINER_STATE",
                            source="docker", resource_identifier=container.name,
                            metadata={
                                "status": container.status,
                                "cpu_percent": container.cpu_percent,
                                "memory_bytes": container.memory_bytes,
                                "restart_count": container.restart_count,
                                "exit_code": container.exit_code,
                                "logs": container.logs,
                                "labels": container.labels,
                            }, observed_at=container.last_observation,
                        )
            self.record_incident_event(
                incident_id=incident.id, event_type="EVIDENCE_CAPTURED",
                description="Infrastructure telemetry evidence collected",
                source="system",
            )
            self.db.flush()
        except Exception as exc:
            logger.warning("Live incident evidence collection failed: %s", exc)

    def get_incident_summary(self) -> dict:
        """Get summary statistics for incident dashboard."""
        now = datetime.now(UTC)
        one_day_ago = now - timedelta(days=1)

        # Active incidents (not RESOLVED or CLOSED)
        active_statuses = ["DETECTED", "INVESTIGATING", "IDENTIFIED", "RESOLVING"]

        total_active = self.db.execute(
            select(func.count()).where(Incident.status.in_(active_statuses))
        ).scalar_one()

        critical_count = self.db.execute(
            select(func.count()).where(
                and_(Incident.status.in_(active_statuses), Incident.severity == "CRITICAL")
            )
        ).scalar_one()

        high_count = self.db.execute(
            select(func.count()).where(
                and_(Incident.status.in_(active_statuses), Incident.severity == "HIGH")
            )
        ).scalar_one()

        warning_count = self.db.execute(
            select(func.count()).where(
                and_(Incident.status.in_(active_statuses), Incident.severity == "WARNING")
            )
        ).scalar_one()

        info_count = self.db.execute(
            select(func.count()).where(
                and_(Incident.status.in_(active_statuses), Incident.severity == "INFO")
            )
        ).scalar_one()

        recently_resolved_count = self.db.execute(
            select(func.count()).where(
                and_(Incident.status == "RESOLVED", Incident.resolved_at >= one_day_ago)
            )
        ).scalar_one()

        # Oldest unresolved incident
        oldest_unresolved = self.db.execute(
            select(Incident)
            .where(Incident.status.in_(active_statuses))
            .order_by(Incident.first_detected_at)
            .limit(1)
        ).scalar_one_or_none()

        # Latest incidents
        latest_incidents = list(
            self.db.execute(
                select(Incident).order_by(desc(Incident.updated_at)).limit(10)
            )
            .scalars()
            .all()
        )

        return {
            "total_active": total_active,
            "critical_count": critical_count,
            "high_count": high_count,
            "warning_count": warning_count,
            "info_count": info_count,
            "recently_resolved_count": recently_resolved_count,
            "oldest_unresolved": oldest_unresolved,
            "latest_incidents": latest_incidents,
        }
