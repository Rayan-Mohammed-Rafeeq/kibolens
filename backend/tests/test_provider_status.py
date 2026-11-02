from app.ai.router.openrouter_provider import _classify_openrouter_status
from app.ai.router.types import FailureCategory


def test_openrouter_upstream_rate_limit_is_not_account_quota():
    assert _classify_openrouter_status(429, "temporarily rate-limited upstream") == FailureCategory.RATE_LIMITED


def test_openrouter_account_quota_is_provider_wide():
    assert _classify_openrouter_status(429, "daily quota exceeded") == FailureCategory.QUOTA_EXHAUSTED
