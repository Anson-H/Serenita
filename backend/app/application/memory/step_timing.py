"""Local timestamps and monotonic elapsed time for one actual step execution."""
from time import monotonic

from backend.app.core.time import local_now_iso


class StepTiming:
    def __init__(self):
        self.started_at = local_now_iso()
        self.started = monotonic()

    def snapshot(self, status):
        return {
            'started_at': self.started_at,
            'finished_at': None if status in {'running', 'retrying'} else local_now_iso(),
            'elapsed_seconds': max(0, monotonic() - self.started),
        }
