"""Simple interval scheduler with overlap prevention.

Deliberately minimal (no APScheduler dependency): a loop runner with
per-job last-run tracking and a lock so overlapping invocations of the
same job never duplicate work. Graceful shutdown via SIGTERM/SIGINT.
"""
from __future__ import annotations

import signal
import threading
import time
from dataclasses import dataclass, field


@dataclass
class ScheduledJob:
    name: str
    func: object
    interval_s: float
    last_run: float = 0.0
    running: bool = False


class Scheduler:
    def __init__(self):
        self.jobs: list[ScheduledJob] = []
        self._stop = threading.Event()
        self._locks: dict[str, threading.Lock] = {}

    def add(self, name: str, func, interval_s: float) -> None:
        self.jobs.append(ScheduledJob(name, func, interval_s))
        self._locks[name] = threading.Lock()

    def _try_run(self, job: ScheduledJob) -> None:
        lock = self._locks[job.name]
        if not lock.acquire(blocking=False):
            return  # overlapping invocation skipped, never duplicated
        try:
            job.func()
            job.last_run = time.monotonic()
        finally:
            lock.release()

    def run_forever(self, tick_s: float = 1.0) -> None:
        import threading as _t
        if _t.current_thread() is _t.main_thread():
            def stop(*_):
                self._stop.set()
            signal.signal(signal.SIGTERM, stop)
            signal.signal(signal.SIGINT, stop)
        while not self._stop.is_set():
            now = time.monotonic()
            for job in self.jobs:
                if now - job.last_run >= job.interval_s:
                    self._try_run(job)
            self._stop.wait(tick_s)

    def shutdown(self) -> None:
        self._stop.set()
