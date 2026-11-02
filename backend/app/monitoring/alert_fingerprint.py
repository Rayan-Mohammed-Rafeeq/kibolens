"""Stable logical alert identity used for recurrence correlation.

This is an independent Python adaptation of the stable identity concept
documented by Akmatori: source, alert name and target are normalized before a
short SHA-256 fingerprint is created. The external Alertmanager fingerprint
is still retained for exact source-level correlation.
"""

from __future__ import annotations

import hashlib
import json


def logical_alert_fingerprint(
    source: str,
    alert_name: str,
    target: str,
) -> str | None:
    """Return a stable recurrence key, or ``None`` when no target is known."""
    normalized_target = target.strip().lower()
    if not normalized_target:
        return None
    payload = json.dumps(
        [source.strip().lower(), alert_name.strip().lower(), normalized_target],
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:32]
