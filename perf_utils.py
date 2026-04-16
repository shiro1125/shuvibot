# perf_utils.py
# MODIFIED: 단계별 성능 로그 분리
import time


class PerfTracker:
    def __init__(self, enabled: bool = True):
        self.enabled = enabled
        self._start = time.perf_counter()
        self._last = self._start

    def log(self, label: str):
        if not self.enabled:
            return
        now = time.perf_counter()
        elapsed_ms = (now - self._last) * 1000
        self._last = now
        print(f"[PERF] {label}: {elapsed_ms:.0f}ms")

    def total(self):
        if not self.enabled:
            return
        total_ms = (time.perf_counter() - self._start) * 1000
        print(f"[PERF] total: {total_ms:.0f}ms")
