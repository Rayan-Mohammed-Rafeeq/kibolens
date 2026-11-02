"""Per-model and per-provider circuit breaker with quota tracking."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from app.ai.router.types import FailureCategory, PROVIDER_WIDE_FAILURE_CATEGORIES

logger = logging.getLogger(__name__)

# Defaults
_CB_FAILURE_THRESHOLD = 5      # failures before opening
_CB_HALF_OPEN_AFTER_SECONDS = 120  # probe window after open
_CB_PROBE_SUCCESSES = 1        # successes needed to close


@dataclass
class _CircuitState:
    """Mutable circuit-breaker state for one key (model or provider)."""

    failures: int = 0
    successes: int = 0
    opened_at: float | None = None  # epoch seconds
    last_failure_category: FailureCategory | None = None
    last_failure_at: float | None = None
    last_success_at: float | None = None
    quota_exhausted: bool = False
    quota_exhausted_at: float | None = None
    half_open_after_seconds: float = _CB_HALF_OPEN_AFTER_SECONDS

    @property
    def is_open(self) -> bool:
        if self.quota_exhausted:
            return True
        if self.opened_at is None:
            return False
        elapsed = time.monotonic() - self.opened_at
        return elapsed < self.half_open_after_seconds

    @property
    def is_half_open(self) -> bool:
        if self.opened_at is None:
            return False
        if self.quota_exhausted:
            return False
        elapsed = time.monotonic() - self.opened_at
        return elapsed >= self.half_open_after_seconds

    def to_dict(self) -> dict:
        return {
            "failures": self.failures,
            "successes": self.successes,
            "is_open": self.is_open,
            "is_half_open": self.is_half_open,
            "opened_at": self.opened_at,
            "last_failure_category": (
                self.last_failure_category.value if self.last_failure_category else None
            ),
            "last_failure_at": self.last_failure_at,
            "last_success_at": self.last_success_at,
            "quota_exhausted": self.quota_exhausted,
        }


class CircuitBreakerRegistry:
    """Registry of circuit-breaker states for models and providers."""

    def __init__(
        self,
        failure_threshold: int = _CB_FAILURE_THRESHOLD,
        half_open_after_seconds: float = _CB_HALF_OPEN_AFTER_SECONDS,
        probe_successes: int = _CB_PROBE_SUCCESSES,
    ):
        self._failure_threshold = failure_threshold
        self._half_open_after = half_open_after_seconds
        self._probe_successes = probe_successes
        self._models: dict[str, _CircuitState] = {}   # key: "provider:model_id"
        self._providers: dict[str, _CircuitState] = {}  # key: provider name

    # ─── public helpers ────────────────────────────────────────────────────

    def is_model_available(self, provider: str, model_id: str) -> bool:
        """Return True if the model circuit is closed or half-open (probe allowed)."""
        state = self._models.get(f"{provider}:{model_id}")
        if state is None:
            return True
        return not state.is_open

    def is_provider_available(self, provider: str) -> bool:
        """Return True if the provider circuit is closed or half-open."""
        state = self._providers.get(provider)
        if state is None:
            return True
        return not state.is_open

    def _get_or_create(self, storage: dict[str, _CircuitState], key: str) -> _CircuitState:
        if key not in storage:
            storage[key] = _CircuitState(half_open_after_seconds=self._half_open_after)
        return storage[key]

    def record_success(self, provider: str, model_id: str) -> None:
        mkey = f"{provider}:{model_id}"
        m_state = self._get_or_create(self._models, mkey)
        p_state = self._get_or_create(self._providers, provider)

        now = time.monotonic()
        for state in (m_state, p_state):
            state.successes += 1
            state.last_success_at = now
            state.quota_exhausted = False
            # Reset failure count; close the circuit
            if state.is_half_open:
                if state.successes >= self._probe_successes:
                    logger.info(
                        "Circuit closed after successful probe: %s/%s",
                        provider,
                        model_id,
                    )
                    state.failures = 0
                    state.opened_at = None
            elif state.is_open:
                pass  # Still open, success during fully open is ignored
            else:
                state.failures = 0

    def record_failure(
        self,
        provider: str,
        model_id: str,
        category: FailureCategory,
    ) -> None:
        """Record a model failure and update circuit breaker state.
        
        Provider-wide failures (AUTH_FAILURE, QUOTA_EXHAUSTED) immediately open
        the provider circuit and skip remaining models.
        
        Model-specific failures (INVALID_REQUEST, MODALITY_MISMATCH, SAFETY_REFUSAL)
        only quarantine that individual model.
        
        Transient failures (TIMEOUT, SERVER_ERROR, RATE_LIMITED) increment model
        failure count but do NOT open the provider circuit unless threshold reached
        for provider-wide category.
        """
        mkey = f"{provider}:{model_id}"
        m_state = self._get_or_create(self._models, mkey)
        p_state = self._get_or_create(self._providers, provider)

        now = time.monotonic()

        # Provider-wide failures trip the provider circuit immediately
        if category in PROVIDER_WIDE_FAILURE_CATEGORIES:
            logger.warning(
                "Provider-wide failure recorded: provider=%s model=%s category=%s",
                provider,
                model_id,
                category.value,
            )
            p_state.failures += 1
            p_state.last_failure_category = category
            p_state.last_failure_at = now
            if category == FailureCategory.QUOTA_EXHAUSTED:
                p_state.quota_exhausted = True
                p_state.quota_exhausted_at = now
            if p_state.opened_at is None:
                p_state.opened_at = now
                logger.warning("Provider circuit opened: %s (reason: %s)", provider, category.value)
        
        # Model-specific failure: quarantine this model only
        m_state.failures += 1
        m_state.last_failure_category = category
        m_state.last_failure_at = now
        if category == FailureCategory.QUOTA_EXHAUSTED:
            m_state.quota_exhausted = True
        
        # Open model circuit if threshold reached
        if m_state.failures >= self._failure_threshold and m_state.opened_at is None:
            logger.info("Model circuit opened: %s/%s (quarantined after %d failures)", 
                       provider, model_id, m_state.failures)
            m_state.opened_at = now

    def get_model_state(self, provider: str, model_id: str) -> dict:
        state = self._models.get(f"{provider}:{model_id}")
        return state.to_dict() if state else {}

    def get_provider_state(self, provider: str) -> dict:
        state = self._providers.get(provider)
        return state.to_dict() if state else {}

    def all_provider_states(self) -> dict[str, dict]:
        return {p: s.to_dict() for p, s in self._providers.items()}

    def all_model_states(self) -> dict[str, dict]:
        return {k: s.to_dict() for k, s in self._models.items()}
