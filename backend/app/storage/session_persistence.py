from __future__ import annotations

import json
import os
import threading
import uuid
from collections import OrderedDict
from copy import deepcopy
from abc import ABC, abstractmethod
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from backend.app.session_events import SessionEvent, SessionEventCorruptionError, SessionEventFormatError, SessionHeader, validate_contiguous_events
from backend.app.storage.session_recovery import interrupted_turn_closers
from backend.app.storage.paths import (
    PRIVATE_FILE_MODE,
    app_paths,
    ensure_private_directory,
    ensure_private_file,
)


class UnsupportedSessionLogError(SessionEventFormatError):
    """The artifact is not in the current Serenita event format."""


class SessionEventWriteConflictError(SessionEventCorruptionError):
    """A conditional append lost a race with another event writer."""


@dataclass(frozen=True)
class StoredSession:
    header: SessionHeader
    events: tuple[SessionEvent, ...]
    revision: str
    lineage: str = ""


class SessionPersistence(ABC):

    @abstractmethod
    def create(
        self, header: SessionHeader, seed: list[SessionEvent] | None = None
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def append(
        self,
        account_id: str,
        session_id: str,
        events: list[SessionEvent],
        *,
        created_at: int,
        expected_seq: int | None = None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    def load(
        self, account_id: str, session_id: str, *, repair: bool = True
    ) -> StoredSession | None:
        raise NotImplementedError

    def read_from(
        self, account_id: str, session_id: str, from_seq: int
    ) -> StoredSession | None:
        if not isinstance(from_seq, int) or isinstance(from_seq, bool) or from_seq < 0:
            raise ValueError("from_seq must be a non-negative integer")
        stored = self.load(account_id, session_id, repair=False)
        if stored is None:
            return None
        return StoredSession(
            header=stored.header,
            events=stored.events[from_seq:],
            revision=stored.revision,
            lineage=stored.lineage,
        )

    def repair(self, account_id: str, session_id: str) -> StoredSession | None:
        return self.load(account_id, session_id, repair=True)

    @abstractmethod
    def list(self, account_id: str) -> list[SessionHeader]:
        raise NotImplementedError

    @abstractmethod
    def delete(self, account_id: str, session_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def revision(self, account_id: str, session_id: str) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def replace(
        self,
        account_id: str,
        session_id: str,
        events: list[SessionEvent],
        *,
        expected_revision: str,
    ) -> None:
        """Replace an existing event sequence in one transaction after CAS validation."""

        raise NotImplementedError


_THREAD_LOCKS: dict[str, threading.RLock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock(key: str) -> threading.RLock:
    with _THREAD_LOCKS_GUARD:
        return _THREAD_LOCKS.setdefault(key, threading.RLock())


@contextmanager
def _artifact_lock(lock_path: Path) -> Iterator[None]:
    ensure_private_directory(lock_path.parent)
    key = str(lock_path.resolve())
    with _thread_lock(key):
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, PRIVATE_FILE_MODE)
        try:
            try:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX)
            except ImportError:  # pragma: no cover - Windows fallback is process-local.
                pass
            yield
        finally:
            try:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_UN)
            except ImportError:  # pragma: no cover
                pass
            os.close(descriptor)
            ensure_private_file(lock_path)


class JsonlSessionPersistence(SessionPersistence):
    def __init__(self, *, paths=None):
        self.paths = paths or app_paths()
        # Cache only validated snapshots. File identity and change timestamps
        # invalidate reads after any other process writes or replaces a log.
        self._snapshots: OrderedDict[Path, tuple[tuple[int, ...], StoredSession]] = OrderedDict()
        self._snapshot_bytes = 0
        self._snapshot_guard = threading.Lock()

    def _path(self, account_id: str, session_id: str) -> Path:
        return (
            self.paths.account_root(account_id)
            / "conversations"
            / "sessions"
            / f"{session_id}.jsonl"
        )

    def _lock_path(self, account_id: str, session_id: str) -> Path:
        return self._path(account_id, session_id).with_suffix(".jsonl.lock")

    def create(
        self, header: SessionHeader, seed: list[SessionEvent] | None = None
    ) -> None:
        materialized = validate_contiguous_events(seed or [])
        SessionHeader.from_record(header.to_record())
        if header.seed_event_count != len(materialized):
            raise SessionEventCorruptionError(
                "session header seedEventCount does not match its seed"
            )
        path = self._path(header.account_id, header.id)
        with _artifact_lock(self._lock_path(header.account_id, header.id)):
            stored = self._read_locked(path, repair_torn=False)
            if stored is not None:
                if stored.header != header or list(stored.events) != materialized:
                    raise SessionEventCorruptionError(
                        "session already exists with different durable content"
                    )
                return
            self._create_locked(path, header, materialized)

    def append(
        self,
        account_id: str,
        session_id: str,
        events: list[SessionEvent],
        *,
        created_at: int,
        expected_seq: int | None = None,
    ) -> None:
        if not events:
            return
        path = self._path(account_id, session_id)
        with _artifact_lock(self._lock_path(account_id, session_id)):
            stored = self._read_locked(path, repair_torn=True)
            if stored is None:
                raise SessionEventCorruptionError("session artifact is missing")
            if stored.header.account_id != account_id or stored.header.id != session_id:
                raise SessionEventCorruptionError("session header does not match its account_id/path")
            if expected_seq is not None and len(stored.events) != expected_seq:
                raise SessionEventWriteConflictError(
                    f"session changed before conditional append: expected seq "
                    f"{expected_seq}, got {len(stored.events)}"
                )
            validate_contiguous_events(events, start_seq=len(stored.events))
            if any(event.type == "compaction/checkpoint" or (
                event.type == "tool/result" and isinstance(event.surface_op, dict)
            ) for event in events):
                # Replacements also need their earlier source events checked.
                validate_contiguous_events([*stored.events, *events])
            self._append_lines_locked(path, events)
            stat = path.stat()
            self._remember_snapshot(path, stat, StoredSession(
                header=stored.header,
                events=stored.events + tuple(
                    SessionEvent.from_record(json.loads(self._line(event.to_record())))
                    for event in events
                ),
                revision=self._stat_revision(stat),
                lineage=f"{stat.st_dev}:{stat.st_ino}",
            ))

    def load(
        self, account_id: str, session_id: str, *, repair: bool = True
    ) -> StoredSession | None:
        path = self._path(account_id, session_id)
        with _artifact_lock(self._lock_path(account_id, session_id)):
            stored = self._read_locked(path, repair_torn=repair)
            if stored is None:
                return None
            if stored.header.account_id != account_id or stored.header.id != session_id:
                raise SessionEventCorruptionError("session header does not match its account_id/path")
            if not repair:
                return deepcopy(stored)
            closers = interrupted_turn_closers(stored.events)
            if closers:
                self._append_lines_locked(path, closers)
                stored = self._read_locked(path, repair_torn=False)
            return deepcopy(stored)

    def read_from(
        self, account_id: str, session_id: str, from_seq: int
    ) -> StoredSession | None:
        if not isinstance(from_seq, int) or isinstance(from_seq, bool) or from_seq < 0:
            raise ValueError("from_seq must be a non-negative integer")
        path = self._path(account_id, session_id)
        with _artifact_lock(self._lock_path(account_id, session_id)):
            try:
                handle = path.open("rb")
            except FileNotFoundError:
                return None
            with handle:
                raw_header = handle.readline()
                if not raw_header.endswith(b"\n"):
                    raise SessionEventCorruptionError("session header is torn")
                try:
                    header_record = json.loads(raw_header.decode("utf-8"))
                except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                    raise SessionEventCorruptionError(
                        "session header is not valid JSON"
                    ) from exc
                if (
                    not isinstance(header_record, dict)
                    or header_record.get("type") != "session"
                ):
                    raise UnsupportedSessionLogError("unsupported session timeline")
                header = SessionHeader.from_record(header_record)
                if header.account_id != account_id or header.id != session_id:
                    raise SessionEventCorruptionError(
                        "session header does not match its account_id/path"
                    )

                events: list[SessionEvent] = []
                for event_index, raw_line in enumerate(handle):
                    if event_index < from_seq:
                        continue
                    if not raw_line.endswith(b"\n"):
                        raise SessionEventCorruptionError("session log has a torn tail")
                    try:
                        value = json.loads(raw_line.decode("utf-8"))
                        if not isinstance(value, dict):
                            raise SessionEventCorruptionError(
                                "event line must be an object"
                            )
                        event = SessionEvent.from_record(value)
                    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                        raise SessionEventCorruptionError(
                            f"event line {event_index + 2} is not valid JSON"
                        ) from exc
                    if event.seq != event_index:
                        raise SessionEventCorruptionError(
                            f"session event seq gap: expected {event_index}, got {event.seq}"
                        )
                    events.append(event)
            if events:
                validate_contiguous_events(events, start_seq=from_seq)
            stat = path.stat()
            return StoredSession(
                header=header,
                events=tuple(events),
                revision=(
                    f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"
                ),
                lineage=f"{stat.st_dev}:{stat.st_ino}",
            )

    def list(self, account_id: str) -> list[SessionHeader]:
        directory = self.paths.account_root(account_id) / "conversations" / "sessions"
        if not directory.exists():
            return []
        headers: list[SessionHeader] = []
        for path in sorted(directory.glob("*.jsonl")):
            try:
                with _artifact_lock(path.with_suffix(".jsonl.lock")):
                    stored = self._read_locked(path, repair_torn=False)
            except (UnsupportedSessionLogError, SessionEventFormatError):
                continue
            if stored is not None and stored.header.account_id == account_id:
                headers.append(stored.header)
        return headers

    def delete(self, account_id: str, session_id: str) -> None:
        path = self._path(account_id, session_id)
        lock_path = self._lock_path(account_id, session_id)
        with _artifact_lock(lock_path):
            path.unlink(missing_ok=True)
            self._forget_snapshot(path)
        lock_path.unlink(missing_ok=True)

    def revision(self, account_id: str, session_id: str) -> str | None:
        path = self._path(account_id, session_id)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"

    def replace(
        self,
        account_id: str,
        session_id: str,
        events: list[SessionEvent],
        *,
        expected_revision: str,
    ) -> None:
        validate_contiguous_events(events)
        path = self._path(account_id, session_id)
        with _artifact_lock(self._lock_path(account_id, session_id)):
            stored = self._read_locked(path, repair_torn=False)
            if stored is None:
                raise SessionEventCorruptionError("session artifact is missing")
            if stored.revision != expected_revision:
                raise SessionEventCorruptionError("session changed during replacement")
            self._replace_locked(path, stored.header, events)

    def _read_locked(self, path: Path, *, repair_torn: bool) -> StoredSession | None:
        if not path.exists():
            self._forget_snapshot(path)
            return None
        ensure_private_file(path)
        stat = path.stat()
        with self._snapshot_guard:
            cached = self._snapshots.get(path)
            if cached and cached[0] == self._stat_signature(stat):
                self._snapshots.move_to_end(path)
                return cached[1]
        content = path.read_bytes()
        if not content:
            raise UnsupportedSessionLogError("empty session timeline")
        lines = content.splitlines(keepends=True)
        if not lines or not lines[0].endswith(b"\n"):
            raise SessionEventCorruptionError("session header is torn")
        try:
            header_record = json.loads(lines[0].decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise SessionEventCorruptionError("session header is not valid JSON") from exc
        if not isinstance(header_record, dict) or header_record.get("type") != "session":
            raise UnsupportedSessionLogError("unsupported session timeline")
        header = SessionHeader.from_record(header_record)

        parsed: list[SessionEvent] = []
        line_offsets: list[int] = []
        offset = len(lines[0])
        torn_at: int | None = None
        for line_index, raw_line in enumerate(lines[1:]):
            line_offsets.append(offset)
            if not raw_line.endswith(b"\n"):
                torn_at = offset
                break
            try:
                value = json.loads(raw_line.decode("utf-8"))
                if not isinstance(value, dict):
                    raise SessionEventCorruptionError("event line must be an object")
                parsed.append(SessionEvent.from_record(value))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise SessionEventCorruptionError(
                    f"event line {line_index + 2} is not valid JSON"
                ) from exc
            offset += len(raw_line)

        last_turn_end = -1
        for index in range(len(parsed) - 1, -1, -1):
            event = parsed[index]
            if event.type == "turn/end":
                last_turn_end = index
                break

        events: list[SessionEvent] = []
        for index, event in enumerate(parsed):
            if event.seq != index:
                raise SessionEventCorruptionError(
                    f"session event seq gap: expected {index}, got {event.seq}"
                )
            events.append(event)

        if torn_at is not None:
            if len(parsed) <= last_turn_end:
                raise SessionEventCorruptionError("session log has a torn committed tail")
            if not repair_torn:
                raise SessionEventCorruptionError("session log has a torn tail")
            with path.open("r+b") as handle:
                handle.truncate(torn_at)
                handle.flush()
                os.fsync(handle.fileno())
            content = content[:torn_at]
        validate_contiguous_events(events)
        stat = path.stat()
        stored = StoredSession(
            header=header,
            events=tuple(events),
            revision=f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}",
            lineage=f"{stat.st_dev}:{stat.st_ino}",
        )
        self._remember_snapshot(path, stat, stored)
        return stored

    @staticmethod
    def _stat_signature(stat) -> tuple[int, ...]:
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    @staticmethod
    def _stat_revision(stat) -> str:
        return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"

    def _forget_snapshot(self, path: Path) -> None:
        with self._snapshot_guard:
            previous = self._snapshots.pop(path, None)
            if previous:
                self._snapshot_bytes -= previous[0][2]

    def _remember_snapshot(self, path: Path, stat, stored: StoredSession) -> None:
        with self._snapshot_guard:
            previous = self._snapshots.pop(path, None)
            if previous:
                self._snapshot_bytes -= previous[0][2]
            if stat.st_size > 8 * 1024 * 1024:
                return
            self._snapshots[path] = (self._stat_signature(stat), stored)
            self._snapshot_bytes += stat.st_size
            while len(self._snapshots) > 64 or self._snapshot_bytes > 8 * 1024 * 1024:
                _, evicted = self._snapshots.popitem(last=False)
                self._snapshot_bytes -= evicted[0][2]

    def _create_locked(
        self, path: Path, header: SessionHeader, events: list[SessionEvent]
    ) -> None:
        ensure_private_directory(path.parent)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = self._line(header.to_record()) + b"".join(
            self._line(event.to_record()) for event in events
        )
        descriptor = os.open(temp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, PRIVATE_FILE_MODE)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temp_path, path)
            except FileExistsError:
                raise SessionEventCorruptionError(
                    f"session artifact already exists: {path.name}"
                )
            finally:
                temp_path.unlink(missing_ok=True)
            self._fsync_directory(path.parent)
            ensure_private_file(path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _replace_locked(
        self, path: Path, header: SessionHeader, events: list[SessionEvent]
    ) -> None:
        ensure_private_directory(path.parent)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        payload = self._line(header.to_record()) + b"".join(
            self._line(event.to_record()) for event in events
        )
        descriptor = os.open(
            temp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, PRIVATE_FILE_MODE
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            self._fsync_directory(path.parent)
            ensure_private_file(path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _append_lines_locked(self, path: Path, events: list[SessionEvent]) -> None:
        payload = b"".join(self._line(event.to_record()) for event in events)
        descriptor = os.open(path, os.O_APPEND | os.O_WRONLY)
        with os.fdopen(descriptor, "ab") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        ensure_private_file(path)

    @staticmethod
    def _line(value: dict[str, Any]) -> bytes:
        try:
            return (
                json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
                + "\n"
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise SessionEventCorruptionError(
                "session record must be losslessly JSON-serializable"
            ) from exc

    @staticmethod
    def _fsync_directory(path: Path) -> None:
        descriptor = os.open(path, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
