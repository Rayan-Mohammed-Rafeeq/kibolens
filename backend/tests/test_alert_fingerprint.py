from app.monitoring.alert_fingerprint import logical_alert_fingerprint


def test_logical_alert_fingerprint_normalizes_identity():
    assert logical_alert_fingerprint("AlertManager", "High CPU", "KIBO:9100") == logical_alert_fingerprint("alertmanager", "high cpu", "kibo:9100")


def test_logical_alert_fingerprint_requires_target():
    assert logical_alert_fingerprint("alertmanager", "High CPU", "") is None
