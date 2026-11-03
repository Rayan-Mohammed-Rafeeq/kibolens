from datetime import datetime, timezone

import pytest

from app.core.config import Settings
from app.models.notification import EmailNotification
from app.models.user import User
from app.monitoring.simulation import SCENARIO_BY_KEY, SIMULATION_SCENARIOS, make_alert
from app.services.incidents import IncidentService
from app.services import notifications
from app.services.notifications import notify_incident, retry_failed_notifications


def test_simulation_alert_is_explicitly_marked():
    alert = make_alert(SCENARIO_BY_KEY["high-memory"])
    assert alert.labels["kibolens_simulated"] == "true"
    assert alert.fingerprint == "simulation:high-memory"


def test_failure_lab_catalog_contains_supported_scenarios_only():
    keys = {scenario.key for scenario in SIMULATION_SCENARIOS}
    assert "interview-demo" not in keys
    assert keys == {
        "high-cpu", "high-memory", "critical-memory", "high-temperature",
        "disk-nearly-full", "container-crash", "container-restart-loop",
        "container-unhealthy", "application-config-failure",
    }


@pytest.mark.asyncio
async def test_simulation_notification_is_idempotent(database):
    settings = Settings(environment="test", incident_notification_emails="demo@example.com")
    service = IncidentService(database)
    incident = service.process_alert(make_alert(SCENARIO_BY_KEY["container-crash"]))
    first = await notify_incident(database, incident, "firing", settings)
    second = await notify_incident(database, incident, "firing", settings)
    assert first[0]["status"] == "accepted"
    assert second[0]["status"] == "duplicate"


def verified_user(database, email="account@example.com"):
    user = User(
        username=email.split("@")[0],
        email=email,
        email_normalized=email,
        password_hash="hash",
        role="admin",
        email_verified_at=datetime.now(timezone.utc),
    )
    database.add(user)
    database.commit()
    return user


@pytest.mark.asyncio
async def test_new_real_incident_notifies_verified_account(monkeypatch, database):
    sent = []

    class CaptureEmail:
        def send_incident_email(self, to, subject, text, html):
            sent.append({"to": to, "subject": subject, "text": text, "html": html})
            return "resend-real-id"

    monkeypatch.setattr(notifications, "MockEmailService", CaptureEmail)
    user = verified_user(database)
    incident = IncidentService(database).process_alert(make_alert(SCENARIO_BY_KEY["high-memory"]))

    result = await notify_incident(database, incident, "firing", Settings(environment="test"), user=user)

    assert result == [{"recipient": "account@example.com", "status": "accepted", "provider_id": "resend-real-id"}]
    assert sent[0]["to"] == user.email
    assert incident.incident_number in sent[0]["text"]
    assert "Open incident:" in sent[0]["text"]


@pytest.mark.asyncio
async def test_simulated_incident_email_is_clearly_labelled(monkeypatch, database):
    sent = []

    class CaptureEmail:
        def send_incident_email(self, to, subject, text, html):
            sent.append((subject, text, html))
            return "mock-demo-id"

    monkeypatch.setattr(notifications, "MockEmailService", CaptureEmail)
    user = verified_user(database, "demo-account@example.com")
    incident = IncidentService(database).process_alert(make_alert(SCENARIO_BY_KEY["container-crash"]))

    await notify_incident(database, incident, "firing", Settings(environment="test"), user=user)

    assert sent[0][0].startswith("[SIMULATED]")
    assert "SIMULATED DEMONSTRATION" in sent[0][1]
    assert "SIMULATED" in sent[0][2]


@pytest.mark.asyncio
async def test_disabled_account_and_unchecked_demo_do_not_send(monkeypatch, database):
    sent = []

    class CaptureEmail:
        def send_incident_email(self, *args):
            sent.append(args)
            return "should-not-send"

    monkeypatch.setattr(notifications, "MockEmailService", CaptureEmail)
    user = verified_user(database, "disabled@example.com")
    user.incident_notifications_enabled = False
    database.commit()
    incident = IncidentService(database).process_alert(make_alert(SCENARIO_BY_KEY["high-memory"]))

    assert await notify_incident(database, incident, "firing", Settings(environment="test"), user=user) == []
    assert sent == []


@pytest.mark.asyncio
async def test_repeated_polls_do_not_duplicate_and_escalation_notifies(monkeypatch, database):
    sent = []

    class CaptureEmail:
        def send_incident_email(self, to, subject, text, html):
            sent.append(subject)
            return f"id-{len(sent)}"

    monkeypatch.setattr(notifications, "MockEmailService", CaptureEmail)
    user = verified_user(database, "escalation@example.com")
    service = IncidentService(database)
    first = service.process_alert(make_alert(SCENARIO_BY_KEY["high-memory"]))
    settings = Settings(environment="test")
    assert (await notify_incident(database, first, "firing", settings, user=user))[0]["status"] == "accepted"
    assert (await notify_incident(database, first, "firing", settings, user=user))[0]["status"] == "duplicate"

    escalated = make_alert(SCENARIO_BY_KEY["critical-memory"])
    escalated.fingerprint = first.alert_fingerprint
    second = service.process_alert(escalated)
    result = await notify_incident(database, second, service.last_notification_event_key, settings, user=user)

    assert result[0]["status"] == "accepted"
    assert len(sent) == 2
    assert database.query(EmailNotification).count() == 2


@pytest.mark.asyncio
async def test_failed_delivery_is_recorded_and_retried(monkeypatch, database):
    attempts = {"count": 0}

    class FlakyEmail:
        def send_incident_email(self, *args):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("provider rejected message")
            return "retry-success"

    monkeypatch.setattr(notifications, "MockEmailService", FlakyEmail)
    user = verified_user(database, "retry@example.com")
    incident = IncidentService(database).process_alert(make_alert(SCENARIO_BY_KEY["high-memory"]))
    settings = Settings(environment="test")

    result = await notify_incident(database, incident, "firing", settings, user=user)
    delivery = database.query(EmailNotification).one()
    assert result[0]["status"] == "failed"
    assert delivery.status == "failed"
    assert delivery.attempts == 1

    assert await retry_failed_notifications(database, settings) == 1
    database.refresh(delivery)
    assert delivery.status == "accepted"
    assert delivery.attempts == 2


@pytest.mark.asyncio
async def test_configured_owner_delivery_is_independent(monkeypatch, database):
    sent: list[str] = []

    class OneRecipientFails:
        def send_incident_email(self, to, subject, text, html):
            sent.append(to)
            if to == "owner-one@example.com":
                raise RuntimeError("owner one unavailable")
            return "owner-two-provider-id"

    monkeypatch.setattr(notifications, "MockEmailService", OneRecipientFails)
    settings = Settings(
        environment="test",
        incident_notification_emails="owner-one@example.com,owner-two@example.com",
    )
    incident = IncidentService(database).process_alert(make_alert(SCENARIO_BY_KEY["high-cpu"]))

    result = await notify_incident(database, incident, "firing", settings)

    assert sent == ["owner-one@example.com", "owner-two@example.com"]
    assert [item["status"] for item in result] == ["failed", "accepted"]
    rows = database.query(EmailNotification).order_by(EmailNotification.recipient).all()
    assert [row.status for row in rows] == ["failed", "accepted"]


def test_incident_reuses_logical_identity_when_external_fingerprint_changes(database):
    service = IncidentService(database)
    first = service.process_alert(make_alert(SCENARIO_BY_KEY["high-memory"]))
    changed = make_alert(SCENARIO_BY_KEY["high-memory"])
    changed.fingerprint = "different-source-fingerprint"
    second = service.process_alert(changed)
    assert second.id == first.id
    assert first.logical_fingerprint
