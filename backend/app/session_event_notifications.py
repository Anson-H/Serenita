from __future__ import annotations

import threading


class SessionEventNotifications:
    """Wake live readers after a session event append has durably committed."""

    def __init__(self) -> None:
        self._condition = threading.Condition()
        self._latest_seq_by_session: dict[tuple[str, str], int] = {}

    @staticmethod
    def _key(account_id: str, session_id: str) -> tuple[str, str]:
        return account_id, session_id

    def publish(self, account_id: str, session_id: str, latest_seq: int) -> None:
        key = self._key(account_id, session_id)
        with self._condition:
            self._latest_seq_by_session[key] = max(
                latest_seq,
                self._latest_seq_by_session.get(key, -1),
            )
            self._condition.notify_all()

    def has_events_from(self, account_id: str, session_id: str, from_seq: int) -> bool:
        key = self._key(account_id, session_id)
        with self._condition:
            return self._latest_seq_by_session.get(key, -1) >= from_seq

    def wait_for_events(
        self,
        account_id: str,
        session_id: str,
        from_seq: int,
        *,
        timeout: float,
    ) -> bool:
        key = self._key(account_id, session_id)
        with self._condition:
            return self._condition.wait_for(
                lambda: self._latest_seq_by_session.get(key, -1) >= from_seq,
                timeout=max(0.0, timeout),
            )



