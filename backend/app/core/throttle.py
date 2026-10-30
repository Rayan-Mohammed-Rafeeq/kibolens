from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta


class LoginThrottle:
    def __init__(self, maximum_attempts: int, window: timedelta = timedelta(minutes=15)) -> None:
        self.maximum_attempts = maximum_attempts
        self.window = window
        self.attempts: dict[str, deque[datetime]] = defaultdict(deque)

    def is_limited(self, key: str) -> bool:
        self._prune(key)
        return len(self.attempts[key]) >= self.maximum_attempts

    def record_failure(self, key: str) -> None:
        self._prune(key)
        self.attempts[key].append(datetime.now(UTC))

    def clear(self, key: str) -> None:
        self.attempts.pop(key, None)

    def _prune(self, key: str) -> None:
        cutoff = datetime.now(UTC) - self.window
        attempts = self.attempts[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()
