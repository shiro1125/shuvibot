# cache_store.py
# MODIFIED: 공용 TTL 캐시 유틸 분리
import time
from threading import RLock
from typing import Dict, Generic, Optional, TypeVar

T = TypeVar("T")


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float):
        self.ttl_seconds = ttl_seconds
        self._data: Dict[str, tuple[float, T]] = {}
        self._lock = RLock()

    def get(self, key: str) -> Optional[T]:
        with self._lock:
            item = self._data.get(key)
            if not item:
                return None
            created_at, value = item
            if time.monotonic() - created_at > self.ttl_seconds:
                self._data.pop(key, None)
                return None
            return value

    def set(self, key: str, value: T):
        with self._lock:
            self._data[key] = (time.monotonic(), value)

    def delete_prefix(self, prefix: str):
        with self._lock:
            for key in list(self._data.keys()):
                if key.startswith(prefix):
                    self._data.pop(key, None)

    def clear(self):
        with self._lock:
            self._data.clear()
