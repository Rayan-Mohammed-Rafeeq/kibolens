from collections import deque


class AlertDeduplicator:
    def __init__(self, maximum_entries: int = 1000) -> None:
        self.maximum_entries = maximum_entries
        self._fingerprints: deque[str] = deque()
        self._seen: set[str] = set()

    def accept(self, fingerprint: str) -> bool:
        if fingerprint in self._seen:
            return False
        self._seen.add(fingerprint)
        self._fingerprints.append(fingerprint)
        if len(self._fingerprints) > self.maximum_entries:
            self._seen.remove(self._fingerprints.popleft())
        return True
