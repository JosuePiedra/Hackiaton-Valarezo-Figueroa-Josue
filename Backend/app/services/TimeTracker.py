import time
import contextlib
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class TimeTracker:
    """Lightweight timing utility — no DB persistence (rag_core MVP)."""

    def __init__(self, name: str):
        self.name = name
        self.start_time = time.time()
        self.intervals: dict = {}
        self.checkpoints: dict = {"start": self.start_time}
        self.current_checkpoint = "start"

    def checkpoint(self, name: str) -> "TimeTracker":
        current = time.time()
        self.intervals[f"{self.current_checkpoint}_to_{name}"] = (
            current - self.checkpoints[self.current_checkpoint]
        )
        self.checkpoints[name] = current
        self.current_checkpoint = name
        return self

    def finish(self, log_level: int = logging.DEBUG) -> float:
        end = time.time()
        total = end - self.start_time
        self.intervals[f"{self.current_checkpoint}_to_end"] = (
            end - self.checkpoints[self.current_checkpoint]
        )
        logger.log(log_level, f"[{self.name}] total={total:.4f}s | {self.intervals}")
        return total

    @contextlib.contextmanager
    def measure(self, name: str):
        start = time.time()
        try:
            yield
        finally:
            self.intervals[name] = time.time() - start

    def get_elapsed_time(self, measure_name: Optional[str] = None) -> float:
        if measure_name and measure_name in self.intervals:
            return self.intervals[measure_name]
        return time.time() - self.start_time
