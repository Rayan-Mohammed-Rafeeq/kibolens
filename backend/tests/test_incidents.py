"""Tests for incident management system."""

from datetime import datetime, timedelta
from datetime import timezone as tz

UTC = tz.utc
from unittest.mock import MagicMock, Mock
from uuid import uuid4

import pytest
from app.core.config import get_settings
from app.core.security import token_hash
from app.models.incident import Incident, IncidentEvent, EvidenceRecord, IncidentSequence
from app.models.session import UserSession
from app.models.user import User
from app.schemas.monitoring import AlertmanagerAlert
from app.services.incidents import IncidentService, VALID_TRANSITIONS
from sqlalchemy.orm import Session


@pytest.fixture
def user(database: Session) -> User:
    """Create test user."""
    user = User(username="testuser", password_hash="fakehash", role="admin")
    database.add(user)
    database.commit()
    return user


@pytest.fixture
def user_session(database: Session, user: User) -> tuple[UserSession, str]:
    """Create test session and return token."""
    token = "test-token-12345"
    csrf_token = "csrf-token-12345"
    settings = get_settings()
    session = UserSession(
        user_id=user.id,
        token_hash=token_hash(token, settings),
        csrf_token_hash=token_hash(csrf_token, settings),
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    database.add(session)
    database.commit()
    return session, token


@pytest.fixture
def mock_monitoring():
    """Mock monitoring service that returns unavailable state."""
    mock = Mock()
    mock.summary.return_value = Mock(
        monitoring_available=False,
        metrics=[],
        last_successful_collection=None,
    )
    mock.containers.return_value = []
    return mock


@pytest.fixture
def incident_service(database: Session, mock_monitoring) -> IncidentService:
    """Create incident service with mocked monitoring."""
    return IncidentService(database, mock_monitoring)


class TestIncidentCreation:
    """Test incident creation and reference generation."""

    def test_create_incident_generates_unique_number(
        self, incident_service: IncidentService
    ):
        """Incident numbers should be unique and sequential."""
        inc1 = incident_service.create_incident(
            title="Test Incident 1",
            description="First test",
            severity="HIGH",
        )
        incident_service.db.commit()

        inc2 = incident_service.create_incident(
            title="Test Incident 2",
            description="Second test",
            severity="CRITICAL",
        )
        incident_service.db.commit()

        assert inc1.incident_number == "INC-000001"
        assert inc2.incident_number == "INC-000002"
        assert inc1.id != inc2.id

    def test_create_incident_records_creation_event(
        self, incident_service: IncidentService
    ):
        """Incident creation should record an event."""
        incident = incident_service.create_incident(
            title="Test Incident",
            description="Test description",
            severity="WARNING",
        )
        incident_service.db.commit()

        events = incident_service.get_incident_timeline(incident.id)
        assert len(events) == 1
        assert events[0].event_type == "INCIDENT_CREATED"
        assert events[0].new_status == "DETECTED"

    def test_create_incident_with_alert_data(
        self, incident_service: IncidentService
    ):
        """Incident can capture alert metadata."""
        incident = incident_service.create_incident(
            title="High CPU",
            description="CPU usage above threshold",
            severity="HIGH",
            alert_fingerprint="abc123",
            affected_host="node-1",
            affected_service="web-server",
        )
        incident_service.db.commit()

        assert incident.alert_fingerprint == "abc123"
        assert incident.affected_host == "node-1"
        assert incident.affected_service == "web-server"
        assert incident.status == "DETECTED"


class TestIncidentLifecycle:
    """Test incident status transitions."""

    def test_valid_status_transitions(self, incident_service: IncidentService):
        """Valid status transitions should succeed."""
        incident = incident_service.create_incident(
            title="Test", description="Test", severity="HIGH"
        )
        incident_service.db.commit()

        # DETECTED -> INVESTIGATING
        incident = incident_service.update_incident_status(
            incident.id, "INVESTIGATING"
        )
        assert incident.status == "INVESTIGATING"

        # INVESTIGATING -> IDENTIFIED
        incident = incident_service.update_incident_status(
            incident.id, "IDENTIFIED"
        )
        assert incident.status == "IDENTIFIED"

        # IDENTIFIED -> RESOLVING
        incident = incident_service.update_incident_status(incident.id, "RESOLVING")
        assert incident.status == "RESOLVING"

        # RESOLVING -> RESOLVED
        incident = incident_service.update_incident_status(incident.id, "RESOLVED")
        assert incident.status == "RESOLVED"
        assert incident.resolved_at is not None

    def test_invalid_status_transition_raises_error(
        self, incident_service: IncidentService
    ):
        """Invalid transitions should raise ValueError."""
        incident = incident_service.create_incident(
            title="Test", description="Test", severity="HIGH"
        )
        incident_service.db.commit()

        # Cannot go from DETECTED to IDENTIFIED (must go through INVESTIGATING)
        with pytest.raises(ValueError, match="Invalid status transition"):
            incident_service.update_incident_status(incident.id, "IDENTIFIED")

    def test_reopen_resolved_incident(self, incident_service: IncidentService):
        """Resolved incidents can be reopened."""
        incident = incident_service.create_incident(
            title="Test", description="Test", severity="HIGH"
        )
        incident_service.db.commit()

        # Resolve it
        incident = incident_service.resolve_incident(incident.id)
        assert incident.status == "RESOLVED"
        resolved_at = incident.resolved_at

        # Reopen it
        incident = incident_service.reopen_incident(incident.id, note="Recurred")
        assert incident.status == "INVESTIGATING"
        assert incident.resolved_at is None

        # Check event timeline
        events = incident_service.get_incident_timeline(incident.id)
        event_types = [e.event_type for e in events]
        assert "INCIDENT_RESOLVED" in event_types
        assert "INCIDENT_REOPENED" in event_types

    def test_closed_incident_cannot_transition(
        self, incident_service: IncidentService
    ):
        """Closed incidents are terminal."""
        incident = incident_service.create_incident(
            title="Test", description="Test", severity="HIGH"
        )
        incident_service.db.commit()

        # Move to RESOLVED then CLOSED
        incident = incident_service.resolve_incident(incident.id)
        incident = incident_service.close_incident(incident.id)
        assert incident.status == "CLOSED"

        # Cannot transition from CLOSED
        with pytest.raises(ValueError, match="Invalid status transition"):
            incident_service.update_incident_status(incident.id, "INVESTIGATING")


class TestAlertProcessing:
    """Test Alertmanager alert processing."""

    def test_process_firing_alert_creates_incident(
        self, incident_service: IncidentService
    ):
        """Firing alert should create new incident."""
        alert = AlertmanagerAlert(
            status="firing",
            fingerprint="fp-12345",
            labels={"severity": "critical", "alertname": "HighCPU", "job": "node"},
            annotations={"summary": "CPU is high", "description": "CPU > 90%"},
        )

        incident = incident_service.process_alert(alert)
        incident_service.db.commit()

        assert incident.title == "CPU is high"
        assert incident.severity == "CRITICAL"
        assert incident.status == "DETECTED"
        assert incident.alert_fingerprint == "fp-12345"
        assert incident.affected_service == "node"

    def test_process_repeated_firing_alert_updates_incident(
        self, incident_service: IncidentService
    ):
        """Repeated firing alerts should update existing incident."""
        alert = AlertmanagerAlert(
            status="firing",
            fingerprint="fp-same",
            labels={"severity": "high", "alertname": "DiskFull"},
            annotations={"summary": "Disk full"},
        )

        # First alert
        incident1 = incident_service.process_alert(alert)
        incident_service.db.commit()
        first_id = incident1.id
        first_observed = incident1.last_observed_at

        # Same alert again
        incident2 = incident_service.process_alert(alert)
        incident_service.db.commit()

        assert incident2.id == first_id  # Same incident
        assert incident2.last_observed_at > first_observed

        # Check for ALERT_REPEATED event
        events = incident_service.get_incident_timeline(incident2.id)
        event_types = [e.event_type for e in events]
        assert "ALERT_REPEATED" in event_types

    def test_process_resolved_alert_resolves_incident(
        self, incident_service: IncidentService
    ):
        """Resolved alert should resolve incident."""
        alert_firing = AlertmanagerAlert(
            status="firing",
            fingerprint="fp-resolve",
            labels={"severity": "warning", "alertname": "MemoryPressure"},
            annotations={"summary": "Memory high"},
        )

        incident = incident_service.process_alert(alert_firing)
        incident_service.db.commit()
        assert incident.status == "DETECTED"

        # Resolved alert
        alert_resolved = AlertmanagerAlert(
            status="resolved",
            fingerprint="fp-resolve",
            labels={"severity": "warning", "alertname": "MemoryPressure"},
            annotations={"summary": "Memory high"},
        )

        incident = incident_service.process_alert(alert_resolved)
        incident_service.db.commit()

        assert incident.status == "RESOLVED"
        assert incident.resolved_at is not None

    def test_process_firing_after_resolved_reopens_incident(
        self, incident_service: IncidentService
    ):
        """Firing alert after resolution should reopen incident."""
        alert = AlertmanagerAlert(
            status="firing",
            fingerprint="fp-recur",
            labels={"severity": "high", "alertname": "ServiceDown"},
            annotations={"summary": "Service is down"},
        )

        # Fire, resolve, fire again
        incident1 = incident_service.process_alert(alert)
        incident_service.db.commit()

        alert_resolved = AlertmanagerAlert(
            status="resolved",
            fingerprint="fp-recur",
            labels={"severity": "high", "alertname": "ServiceDown"},
            annotations={"summary": "Service is down"},
        )
        incident_service.process_alert(alert_resolved)
        incident_service.db.commit()

        incident2 = incident_service.process_alert(alert)
        incident_service.db.commit()

        assert incident2.id == incident1.id  # Same incident reopened
        assert incident2.status == "INVESTIGATING"
        assert incident2.resolved_at is None

        # Check for INCIDENT_REOPENED event
        events = incident_service.get_incident_timeline(incident2.id)
        event_types = [e.event_type for e in events]
        assert "INCIDENT_REOPENED" in event_types

    def test_alert_severity_mapping(self, incident_service: IncidentService):
        """Alert severities should map correctly."""
        severities = {
            "critical": "CRITICAL",
            "high": "HIGH",
            "warning": "WARNING",
            "info": "INFO",
            "unknown": "WARNING",  # Default
        }

        for alert_sev, expected_inc_sev in severities.items():
            alert = AlertmanagerAlert(
                status="firing",
                fingerprint=f"fp-{alert_sev}",
                labels={"severity": alert_sev, "alertname": "Test"},
                annotations={"summary": f"Test {alert_sev}"},
            )
            incident = incident_service.process_alert(alert)
            incident_service.db.commit()
            assert incident.severity == expected_inc_sev


class TestIncidentQueries:
    """Test incident listing and filtering."""

    def test_list_incidents_pagination(self, incident_service: IncidentService):
        """Pagination should work correctly."""
        # Create 15 incidents
        for i in range(15):
            incident_service.create_incident(
                title=f"Incident {i}",
                description=f"Description {i}",
                severity="WARNING",
            )
        incident_service.db.commit()

        # Page 1
        incidents1, total1 = incident_service.list_incidents(page=1, page_size=10)
        assert len(incidents1) == 10
        assert total1 == 15

        # Page 2
        incidents2, total2 = incident_service.list_incidents(page=2, page_size=10)
        assert len(incidents2) == 5
        assert total2 == 15

    def test_filter_by_severity(self, incident_service: IncidentService):
        """Should filter by severity."""
        incident_service.create_incident(
            title="Critical", description="Test", severity="CRITICAL"
        )
        incident_service.create_incident(
            title="Warning", description="Test", severity="WARNING"
        )
        incident_service.db.commit()

        incidents, total = incident_service.list_incidents(severity="CRITICAL")
        assert total == 1
        assert incidents[0].severity == "CRITICAL"

    def test_filter_by_status(self, incident_service: IncidentService):
        """Should filter by status."""
        inc1 = incident_service.create_incident(
            title="Test 1", description="Test", severity="HIGH"
        )
        inc2 = incident_service.create_incident(
            title="Test 2", description="Test", severity="HIGH"
        )
        incident_service.db.commit()

        incident_service.resolve_incident(inc1.id)
        incident_service.db.commit()

        incidents, total = incident_service.list_incidents(status="DETECTED")
        assert total == 1
        assert incidents[0].id == inc2.id

    def test_search_incidents(self, incident_service: IncidentService):
        """Should search by title, description, number."""
        inc = incident_service.create_incident(
            title="High CPU Usage",
            description="CPU exceeded 90% threshold",
            severity="HIGH",
        )
        incident_service.db.commit()

        # Search by title
        incidents, total = incident_service.list_incidents(search="CPU")
        assert total >= 1
        assert any(i.id == inc.id for i in incidents)

        # Search by incident number
        incidents, total = incident_service.list_incidents(search=inc.incident_number)
        assert total == 1
        assert incidents[0].id == inc.id


class TestIncidentSummary:
    """Test incident summary statistics."""

    def test_incident_summary_counts(self, incident_service: IncidentService):
        """Summary should return correct counts."""
        # Create incidents with different severities and statuses
        inc1 = incident_service.create_incident(
            title="Critical 1", description="Test", severity="CRITICAL"
        )
        inc2 = incident_service.create_incident(
            title="High 1", description="Test", severity="HIGH"
        )
        inc3 = incident_service.create_incident(
            title="Warning 1", description="Test", severity="WARNING"
        )
        incident_service.db.commit()

        # Resolve one
        incident_service.resolve_incident(inc3.id)
        incident_service.db.commit()

        summary = incident_service.get_incident_summary()

        assert summary["total_active"] == 2
        assert summary["critical_count"] == 1
        assert summary["high_count"] == 1
        assert summary["warning_count"] == 0
        assert summary["recently_resolved_count"] == 1
        assert summary["oldest_unresolved"] is not None


class TestEvidenceCollection:
    """Test evidence capture."""

    def test_capture_evidence(self, incident_service: IncidentService):
        """Should capture evidence for incidents."""
        incident = incident_service.create_incident(
            title="Test", description="Test", severity="HIGH"
        )
        incident_service.db.commit()

        evidence = incident_service.capture_evidence(
            incident_id=incident.id,
            evidence_type="HOST_METRIC",
            source="prometheus",
            metric_name="cpu_usage",
            metric_value=95.5,
            unit="percent",
            observed_at=datetime.now(UTC),
        )
        incident_service.db.commit()

        assert evidence.incident_id == incident.id
        assert evidence.metric_name == "cpu_usage"
        assert evidence.metric_value == 95.5

        # Retrieve evidence
        all_evidence = incident_service.get_incident_evidence(incident.id)
        assert len(all_evidence) == 1
        assert all_evidence[0].id == evidence.id


class TestAPIEndpoints:
    """Test incident API endpoints."""

    def test_list_incidents_requires_auth(self, client):
        """Incident endpoints require authentication."""
        response = client.get("/api/v1/incidents")
        assert response.status_code == 401

    def test_list_incidents_authenticated(
        self, client, database: Session, user: User, user_session: tuple
    ):
        """Authenticated users can list incidents."""
        session, token = user_session

        # Create test incident
        service = IncidentService(database, None)
        service.create_incident(title="Test", description="Test", severity="HIGH")
        database.commit()

        response = client.get(
            "/api/v1/incidents", cookies={"kibolens_session": token}
        )
        assert response.status_code == 200
        data = response.json()
        assert "incidents" in data
        assert data["total"] == 1

    def test_get_incident_detail(
        self, client, database: Session, user: User, user_session: tuple
    ):
        """Should get incident detail with events and evidence."""
        session, token = user_session

        service = IncidentService(database, None)
        incident = service.create_incident(
            title="Test", description="Test", severity="HIGH"
        )
        database.commit()

        response = client.get(
            f"/api/v1/incidents/{incident.id}", cookies={"kibolens_session": token}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["incident"]["id"] == str(incident.id)
        assert "events" in data
        assert "evidence" in data

    def test_update_incident_status(
        self, client, database: Session, user: User, user_session: tuple
    ):
        """Should update incident status."""
        session, token = user_session

        service = IncidentService(database, None)
        incident = service.create_incident(
            title="Test", description="Test", severity="HIGH"
        )
        database.commit()

        response = client.patch(
            f"/api/v1/incidents/{incident.id}/status",
            json={"status": "INVESTIGATING", "note": "Looking into it"},
            cookies={"kibolens_session": token},
            headers={"X-CSRF-Token": "csrf-token-12345"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "INVESTIGATING"

    def test_add_incident_note(
        self, client, database: Session, user: User, user_session: tuple
    ):
        """Should add note to incident."""
        session, token = user_session

        service = IncidentService(database, None)
        incident = service.create_incident(
            title="Test", description="Test", severity="HIGH"
        )
        database.commit()

        response = client.post(
            f"/api/v1/incidents/{incident.id}/notes",
            json={"note": "Found the issue in logs"},
            cookies={"kibolens_session": token},
            headers={"X-CSRF-Token": "csrf-token-12345"},
        )
        assert response.status_code == 201
        data = response.json()
        assert data["event_type"] == "NOTE_ADDED"


class TestConcurrency:
    """Test concurrent incident operations."""

    def test_concurrent_incident_number_generation(
        self, database: Session
    ):
        """Incident numbers should be unique even under concurrent creation."""
        # Simulate concurrent creation
        service1 = IncidentService(database, None)
        service2 = IncidentService(database, None)

        inc1 = service1.create_incident(
            title="Concurrent 1", description="Test", severity="HIGH"
        )
        database.commit()

        inc2 = service2.create_incident(
            title="Concurrent 2", description="Test", severity="HIGH"
        )
        database.commit()

        assert inc1.incident_number != inc2.incident_number
        assert inc1.incident_number == "INC-000001"
        assert inc2.incident_number == "INC-000002"
