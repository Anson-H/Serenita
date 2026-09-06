"""Own cancellation signals for capability probes within one data root."""

import threading
from pathlib import Path
from backend.app.core.cancellation import CancellationToken


class ModelProbeTasks:
    def __init__(self):
        self._lock = threading.Lock()
        self._tokens: dict[tuple[str, str], CancellationToken] = {}

    def begin(self, account_id: str, model_id: str) -> CancellationToken:
        key = (account_id, model_id)
        token = CancellationToken()
        with self._lock:
            previous = self._tokens.get(key)
            self._tokens[key] = token
        if previous is not None:
            previous.cancel()
        return token

    def finish(self, account_id: str, model_id: str, token: CancellationToken) -> None:
        key = (account_id, model_id)
        with self._lock:
            if self._tokens.get(key) is token:
                self._tokens.pop(key, None)

    def cancel(self, account_id: str, model_id: str) -> None:
        with self._lock:
            token = self._tokens.get((account_id, model_id))
        if token is not None:
            token.cancel()


_registry_lock = threading.Lock()
_tasks: dict[Path, ModelProbeTasks] = {}


def probes_for_paths(paths) -> ModelProbeTasks:
    with _registry_lock:
        return _tasks.setdefault(paths.root.resolve(), ModelProbeTasks())
