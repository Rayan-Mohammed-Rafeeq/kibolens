import pytest

from app.core.config import Settings
from app.monitoring.simulation import SCENARIO_BY_KEY, make_alert
from app.services.incidents import IncidentService
from app.services.notifications import notify_incident


def test_simulation_alert_is_explicitly_marked():
    alert = make_alert(SCENARIO_BY_KEY["high-memory"])
    assert alert.labels["kibolens_simulated"] == "true"
    assert alert.fingerprint == "simulation:high-memory"


@pytest.mark.asyncio
async def test_simulation_notification_is_idempotent(database):
    settings = Settings(environment="test", incident_notification_emails="demo@example.com")
    service = IncidentService(database)
    incident = service.process_alert(make_alert(SCENARIO_BY_KEY["container-crash"]))
    first = await notify_incident(database, incident, "firing", settings)
    second = await notify_incident(database, incident, "firing", settings)
    assert first[0]["status"] == "sent"
    assert second[0]["status"] == "duplicate"
