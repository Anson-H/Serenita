"""定义会话头、事件类型及其字段校验，供 JSONL 读写和投影共同使用。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any, Iterable, Mapping


SESSION_FORMAT_VERSION = 2

SESSION_EVENT_TYPES = frozenset(
    {
        "turn/start",
        "turn/thinking_mode_changed",
        "turn/end",
        "step/start",
        "step/end",
        "user/message",
        "user/message-update",
        "request/header",
        "request/context",
        "assistant/chunk",
        "assistant/message",
        "assistant/message-update",
        "model/result",
        "harness/observation",
        "tool/call",
        "tool/result",
        "resource/attached",
        "workflow/trace",
        "compaction/checkpoint",
        "compaction/status",
        "input/queued",
        "input/queue-reordered",
        "input/queue-removed",
    }
)

SURFACE_EVENT_TYPES = frozenset(
    {
        "user/message",
        "assistant/message",
        "tool/result",
        "compaction/checkpoint",
    }
)

_REQUIRED_DATA_FIELDS: dict[str, frozenset[str]] = {
    "turn/start": frozenset({"turn_id", "user_message_id", "stream_id"}),
    "turn/thinking_mode_changed": frozenset(
        {"turn_id", "requested_mode", "effective_mode", "reasons"}
    ),
    "turn/end": frozenset({"turn_id", "reason"}),
    "step/start": frozenset({"turn_id", "step", "purpose"}),
    "step/end": frozenset({"turn_id", "step"}),
    "user/message": frozenset(
        {"turn_id", "message_id", "parent_message_id", "content"}
    ),
    "user/message-update": frozenset({"message_id", "patch"}),
    "request/header": frozenset(
        {"turn_id", "step", "call_id", "purpose", "header"}
    ),
    "request/context": frozenset({"turn_id", "step", "call_id", "context"}),
    "assistant/chunk": frozenset({"turn_id", "step", "call_id", "chunk"}),
    "assistant/message": frozenset(
        {"turn_id", "message_id", "parent_message_id", "content"}
    ),
    "assistant/message-update": frozenset({"message_id", "patch"}),
    "model/result": frozenset({"turn_id", "step", "call_id", "result"}),
    "harness/observation": frozenset(
        {"turn_id", "step", "observation", "status"}
    ),
    "tool/call": frozenset(
        {"turn_id", "call_id", "tool_call_id", "name", "arguments"}
    ),
    "tool/result": frozenset(
        {"turn_id", "call_id", "tool_call_id", "name", "result", "status"}
    ),
    "resource/attached": frozenset(
        {
            "resource_id",
            "original_filename",
            "mime_type",
            "size_bytes",
            "relative_path",
            "sha256",
        }
    ),
    "workflow/trace": frozenset({"turn_id", "payload"}),
    "compaction/checkpoint": frozenset(
        {
            "turn_id",
            "message_id",
            "compaction_id",
            "summary",
            "content",
            "replaced_turn_ids",
            "estimated_tokens_before",
            "estimated_tokens_after",
            "target_tokens",
        }
    ),
    "compaction/status": frozenset(
        {
            "turn_id",
            "message_id",
            "status",
            "reason",
            "estimated_tokens_before",
            "target_tokens",
        }
    ),
    "input/queued": frozenset(
        {
            "input_id",
            "content",
            "model_id",
            "thinking_mode",
            "context_resources",
            "created_at",
        }
    ),
    "input/queue-reordered": frozenset({"input_ids"}),
    "input/queue-removed": frozenset({"input_id", "reason"}),
}


class SessionEventError(ValueError):
    """Base class for a malformed or unsupported durable session event."""


class SessionEventFormatError(SessionEventError):
    """The stored session structure is not readable by this build."""


class SessionEventCorruptionError(SessionEventError):
    """A session log violates its durable invariants."""


@dataclass(frozen=True)
class SessionHeader:
    id: str
    account_id: str
    created_at: int
    parent_session_id: str | None = None
    seed_event_count: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise SessionEventCorruptionError(
                "session header id must be a non-empty string"
            )
        if not isinstance(self.account_id, str) or not self.account_id:
            raise SessionEventCorruptionError(
                "session header account_id must be a non-empty string"
            )
        if (
            not isinstance(self.created_at, int)
            or isinstance(self.created_at, bool)
            or self.created_at < 0
        ):
            raise SessionEventCorruptionError(
                "session header createdAt must be a non-negative integer"
            )
        if self.parent_session_id is not None and (
            not isinstance(self.parent_session_id, str)
            or not self.parent_session_id
        ):
            raise SessionEventCorruptionError(
                "session header parentSession must be a non-empty string"
            )
        if (
            not isinstance(self.seed_event_count, int)
            or isinstance(self.seed_event_count, bool)
            or self.seed_event_count < 0
        ):
            raise SessionEventCorruptionError(
                "session header seedEventCount must be a non-negative integer"
            )
        if self.parent_session_id is None and self.seed_event_count != 0:
            raise SessionEventCorruptionError(
                "root session header seedEventCount must be zero"
            )
        if self.parent_session_id is not None and self.seed_event_count == 0:
            raise SessionEventCorruptionError(
                "forked session header seedEventCount must be positive"
            )

    def to_record(self) -> dict[str, Any]:
        return {
            "type": "session",
            "version": SESSION_FORMAT_VERSION,
            "id": self.id,
            "accountId": self.account_id,
            "createdAt": self.created_at,
            **(
                {
                    "parentSession": self.parent_session_id,
                    "seedEventCount": self.seed_event_count,
                }
                if self.parent_session_id is not None
                else {}
            ),
        }

    @classmethod
    def from_record(cls, value: Mapping[str, Any]) -> "SessionHeader":
        extra = set(value) - {
            "type",
            "version",
            "id",
            "accountId",
            "createdAt",
            "parentSession",
            "seedEventCount",
        }
        if extra:
            raise SessionEventFormatError(
                f"session header contains unsupported fields: {sorted(extra)}"
            )
        if value.get("type") != "session":
            raise SessionEventFormatError("session log is missing its header")
        if value.get("version") != SESSION_FORMAT_VERSION:
            raise SessionEventFormatError(
                f"unsupported session format version: {value.get('version')!r}"
            )
        has_parent = "parentSession" in value
        has_seed_event_count = "seedEventCount" in value
        if has_parent != has_seed_event_count:
            raise SessionEventFormatError(
                "forked session header must contain parentSession and seedEventCount together"
            )
        if not has_parent and has_seed_event_count:
            raise SessionEventFormatError(
                "root session header must not contain seedEventCount"
            )
        session_id = value.get("id")
        account_id = value.get("accountId")
        created_at = value.get("createdAt")
        parent_session_id = value.get("parentSession")
        seed_event_count = value.get("seedEventCount", 0)
        if not isinstance(session_id, str) or not session_id:
            raise SessionEventCorruptionError("session header id must be a non-empty string")
        if not isinstance(account_id, str) or not account_id:
            raise SessionEventCorruptionError("session header account_id must be a non-empty string")
        if not isinstance(created_at, int) or isinstance(created_at, bool) or created_at < 0:
            raise SessionEventCorruptionError(
                "session header createdAt must be a non-negative integer"
            )
        if has_parent and (
            not isinstance(parent_session_id, str) or not parent_session_id
        ):
            raise SessionEventCorruptionError(
                "session header parentSession must be a non-empty string"
            )
        if (
            not isinstance(seed_event_count, int)
            or isinstance(seed_event_count, bool)
            or seed_event_count < 0
        ):
            raise SessionEventCorruptionError(
                "session header seedEventCount must be a non-negative integer"
            )
        if parent_session_id is None and seed_event_count != 0:
            raise SessionEventCorruptionError(
                "root session header seedEventCount must be zero"
            )
        if parent_session_id is not None and seed_event_count == 0:
            raise SessionEventCorruptionError(
                "forked session header seedEventCount must be positive"
            )
        return cls(
            id=session_id,
            account_id=account_id,
            created_at=created_at,
            parent_session_id=parent_session_id,
            seed_event_count=seed_event_count,
        )


@dataclass(frozen=True)
class SessionEvent:
    type: str
    seq: int
    time: int
    data: dict[str, Any]
    source_event_seqs: tuple[int, ...] | None = None
    surface_op: str | dict[str, Any] | None = None

    def to_record(self) -> dict[str, Any]:
        record: dict[str, Any] = {
            "type": self.type,
            "seq": self.seq,
            "time": self.time,
            "data": self.data,
        }
        if self.source_event_seqs is not None:
            record["sourceEventSeqs"] = list(self.source_event_seqs)
        if self.surface_op is not None:
            record["surfaceOp"] = self.surface_op
        return record

    @classmethod
    def from_record(cls, value: Mapping[str, Any]) -> "SessionEvent":
        extra = set(value) - {
            "type",
            "seq",
            "time",
            "data",
            "sourceEventSeqs",
            "surfaceOp",
        }
        if extra:
            raise SessionEventCorruptionError(
                f"session event contains unsupported envelope fields: {sorted(extra)}"
            )
        event_type = value.get("type")
        if not isinstance(event_type, str) or event_type not in SESSION_EVENT_TYPES:
            raise SessionEventFormatError(f"unknown session event type: {event_type!r}")
        seq = value.get("seq")
        timestamp = value.get("time")
        data = value.get("data")
        if not isinstance(seq, int) or isinstance(seq, bool) or seq < 0:
            raise SessionEventCorruptionError("session event seq must be a non-negative integer")
        if not isinstance(timestamp, int) or isinstance(timestamp, bool) or timestamp < 0:
            raise SessionEventCorruptionError("session event time must be a non-negative integer")
        if not isinstance(data, dict):
            raise SessionEventCorruptionError("session event data must be an object")
        missing = _REQUIRED_DATA_FIELDS[event_type] - set(data)
        if missing:
            raise SessionEventCorruptionError(
                f"{event_type} is missing required data fields: {sorted(missing)}"
            )
        assert_json_value(data, label=f'{event_type}.data')
        _validate_event_data(event_type, data)

        raw_sources = value.get("sourceEventSeqs")
        source_event_seqs: tuple[int, ...] | None = None
        if raw_sources is not None:
            if not isinstance(raw_sources, list) or any(
                not isinstance(item, int)
                or isinstance(item, bool)
                or item < 0
                or item >= seq
                for item in raw_sources
            ):
                raise SessionEventCorruptionError(
                    "sourceEventSeqs must contain earlier non-negative seq values"
                )
            if len(set(raw_sources)) != len(raw_sources):
                raise SessionEventCorruptionError("sourceEventSeqs must not contain duplicates")
            source_event_seqs = tuple(raw_sources)

        surface_op = value.get("surfaceOp")
        if surface_op is not None:
            if event_type not in SURFACE_EVENT_TYPES:
                raise SessionEventCorruptionError(
                    f"{event_type} cannot carry surfaceOp"
                )
            _validate_surface_op(surface_op)
        if event_type == "compaction/checkpoint":
            if not (
                isinstance(surface_op, dict) and surface_op.get("op") == "replace"
            ):
                raise SessionEventCorruptionError(
                    "compaction/checkpoint must replace an earlier model surface"
                )
            if not source_event_seqs:
                raise SessionEventCorruptionError(
                    "compaction/checkpoint sourceEventSeqs must name exact sources"
                )
            if surface_op["end"] > seq:
                raise SessionEventCorruptionError(
                    "compaction/checkpoint surfaceOp must locate an earlier model surface"
                )
        if event_type == "tool/result" and isinstance(surface_op, dict):
            if not source_event_seqs or len(source_event_seqs) != 1:
                raise SessionEventCorruptionError(
                    "tool/result replacement sourceEventSeqs must name exactly one earlier result"
                )
            source_seq = source_event_seqs[0]
            if surface_op != {"op": "replace", "start": source_seq, "end": source_seq + 1}:
                raise SessionEventCorruptionError(
                    "tool/result replacement surfaceOp must locate its exact source"
                )
            if data["status"] not in {"completed", "failed"}:
                raise SessionEventCorruptionError(
                    "tool/result replacement must report a completed or failed outcome"
                )
        return cls(
            type=event_type,
            seq=seq,
            time=timestamp,
            data=dict(data),
            source_event_seqs=source_event_seqs,
            surface_op=surface_op,
        )


def event_now_ms() -> int:
    return time.time_ns() // 1_000_000


def _validate_event_data(event_type: str, data: Mapping[str, Any]) -> None:
    if event_type == "turn/start":
        for name in ("turn_id", "user_message_id", "stream_id"):
            if not isinstance(data[name], str) or not data[name].strip():
                raise SessionEventCorruptionError(f"turn/start {name} must be non-blank text")
    if "session_id" in data:
        raise SessionEventCorruptionError(
            f"{event_type} must not duplicate session_id inside event data"
        )
    if event_type == "input/queued":
        for field in ("input_id", "content", "model_id", "thinking_mode", "created_at"):
            if not isinstance(data.get(field), str):
                raise SessionEventCorruptionError(
                    f"input/queued {field} must be a string"
                )
        if not data.get("input_id"):
            raise SessionEventCorruptionError(
                "input/queued input_id must be a non-empty string"
            )
        if not isinstance(data.get("context_resources"), list):
            raise SessionEventCorruptionError(
                "input/queued context_resources must be an array"
            )
    if event_type == "input/queue-reordered":
        input_ids = data.get("input_ids")
        if (
            not isinstance(input_ids, list)
            or any(not isinstance(item, str) or not item for item in input_ids)
            or len(input_ids) != len(set(input_ids))
        ):
            raise SessionEventCorruptionError(
                "input/queue-reordered input_ids must contain unique non-empty strings"
            )
    if event_type == "input/queue-removed":
        if not isinstance(data.get("input_id"), str) or not data.get("input_id"):
            raise SessionEventCorruptionError(
                "input/queue-removed input_id must be a non-empty string"
            )
        if not isinstance(data.get("reason"), str) or not data.get("reason"):
            raise SessionEventCorruptionError(
                "input/queue-removed reason must be a non-empty string"
            )
    if event_type in {
        "step/start",
        "step/end",
        "request/header",
        "request/context",
        "model/result",
        "harness/observation",
    }:
        step = data.get("step")
        if not isinstance(step, int) or isinstance(step, bool) or step < 1:
            raise SessionEventCorruptionError(
                f"{event_type} step must be a positive integer"
            )
    if event_type == "request/header":
        header = data.get("header")
        if not isinstance(header, dict):
            raise SessionEventCorruptionError("request/header header must be an object")
        if not isinstance(header.get("provider_payload"), dict):
            raise SessionEventCorruptionError(
                "request/header provider_payload must be an object"
            )
        duplicate_input_fields = {
            "system",
            "messages",
            "tools",
            "tool_choice",
            "normalized_request",
        }.intersection(header)
        if duplicate_input_fields:
            raise SessionEventCorruptionError(
                "request/header contains duplicate logical model input"
            )
    if event_type == "request/context":
        context = data.get("context")
        if not isinstance(context, dict):
            raise SessionEventCorruptionError("request/context context must be an object")
        provider_source = context.get("provider_source")
        if (
            not isinstance(provider_source, dict)
            or not isinstance(provider_source.get("path"), str)
        ):
            raise SessionEventCorruptionError(
                "request/context provider_source must contain a JSON Pointer path"
            )
        has_start = "start" in provider_source
        has_end = "end" in provider_source
        if has_start != has_end:
            raise SessionEventCorruptionError(
                "request/context provider_source range must contain start and end"
            )
        if has_start and (
            not isinstance(provider_source["start"], int)
            or isinstance(provider_source["start"], bool)
            or not isinstance(provider_source["end"], int)
            or isinstance(provider_source["end"], bool)
            or provider_source["start"] < 0
            or provider_source["end"] < provider_source["start"]
        ):
            raise SessionEventCorruptionError(
                "request/context provider_source range is invalid"
            )
    if event_type == "harness/observation":
        if not isinstance(data.get("observation"), dict):
            raise SessionEventCorruptionError(
                "harness/observation observation must be an object"
            )
        if data.get("status") not in {"completed", "failed"}:
            raise SessionEventCorruptionError(
                "harness/observation status is invalid"
            )
    if event_type == "assistant/message":
        content = data.get("content")
        if content is not None and not isinstance(content, (str, list)):
            raise SessionEventCorruptionError(
                "assistant/message content must be null, text, or content parts"
            )
        if "tool_calls" in data and not isinstance(data.get("tool_calls"), list):
            raise SessionEventCorruptionError(
                "assistant/message tool_calls must be an array"
            )
        for tool_call in data.get("tool_calls") or []:
            function = tool_call.get("function") if isinstance(tool_call, dict) else None
            if (
                not isinstance(tool_call, dict)
                or not str(tool_call.get("id") or "").strip()
                or not isinstance(function, dict)
                or not str(function.get("name") or "").strip()
            ):
                raise SessionEventCorruptionError(
                    "assistant/message contains an invalid tool call"
                )
        if "branch_addressable" in data and not isinstance(
            data.get("branch_addressable"), bool
        ):
            raise SessionEventCorruptionError(
                "assistant/message branch_addressable must be boolean"
            )
    if event_type in {"tool/call", "tool/result"}:
        if not str(data.get("tool_call_id") or "").strip():
            raise SessionEventCorruptionError(
                f"{event_type} tool_call_id must be a non-empty string"
            )
    if event_type == "tool/result":
        status = data.get("status")
        if status not in {"completed", "failed", "interrupted"}:
            raise SessionEventCorruptionError("tool/result status is invalid")
        if status != "completed" and not isinstance(data.get("error"), dict):
            raise SessionEventCorruptionError(
                "failed or interrupted tool/result must contain an error"
            )
    if event_type in {"compaction/checkpoint", "compaction/status"}:
        identity_field = "compaction_id" if event_type == "compaction/checkpoint" else "message_id"
        compaction_id = data[identity_field]
        if (
            not isinstance(compaction_id, str)
            or not compaction_id.startswith("compaction_")
            or not compaction_id.removeprefix("compaction_").strip()
        ):
            raise SessionEventCorruptionError(
                f"{event_type} {identity_field} must be compaction_<id>"
            )
        for field in ("estimated_tokens_before", "estimated_tokens_after", "target_tokens"):
            if field in data and (
                not isinstance(data[field], int)
                or isinstance(data[field], bool)
                or data[field] < 0
            ):
                raise SessionEventCorruptionError(
                    f"{event_type} {field} must be a non-negative integer"
                )
    if event_type == "compaction/status":
        if not isinstance(data["turn_id"], str) or not data["turn_id"].strip():
            raise SessionEventCorruptionError(
                "compaction/status turn_id must be a non-empty string"
            )
        status = data["status"]
        if status not in ("running", "completed", "failed"):
            raise SessionEventCorruptionError("compaction/status status is invalid")
        if data["reason"] not in ("threshold", "overflow", "tool_result"):
            raise SessionEventCorruptionError("compaction/status reason is invalid")
        if ("estimated_tokens_after" in data) != (status == "completed"):
            raise SessionEventCorruptionError(
                "compaction/status estimated_tokens_after is required only when completed"
            )
        if status == "failed":
            error = data.get("error")
            if not isinstance(error, dict) or any(
                not isinstance(error.get(field), str) or not error[field].strip()
                for field in ("code", "message")
            ):
                raise SessionEventCorruptionError(
                    "compaction/status failed error must contain code and message"
                )
        elif "error" in data:
            raise SessionEventCorruptionError(
                "compaction/status error is allowed only when failed"
            )
    if event_type == "compaction/checkpoint":
        summary = data["summary"]
        if not isinstance(summary, str) or not summary.strip():
            raise SessionEventCorruptionError(
                "compaction/checkpoint summary must be non-empty text"
            )
        if not isinstance(data.get("content"), str) or not data["content"].strip():
            raise SessionEventCorruptionError(
                "compaction/checkpoint content must be non-empty text"
            )
        if not data["content"].startswith(
            f"<compacted-summary>\n{summary}\n</compacted-summary>"
        ):
            raise SessionEventCorruptionError(
                "compaction/checkpoint content must completely wrap summary"
            )
        replaced_turn_ids = data.get("replaced_turn_ids")
        if (
            not isinstance(replaced_turn_ids, list)
            or not replaced_turn_ids
            or any(
                not isinstance(item, str) or not item.strip()
                for item in replaced_turn_ids
            )
        ):
            raise SessionEventCorruptionError(
                "compaction/checkpoint replaced_turn_ids must contain turn ids"
            )


def make_event(
    event_type: str,
    seq: int,
    data: Mapping[str, Any],
    *,
    timestamp: int | None = None,
    source_event_seqs: Iterable[int] | None = None,
    surface_op: str | dict[str, Any] | None = None,
) -> SessionEvent:
    record: dict[str, Any] = {
        "type": event_type,
        "seq": seq,
        "time": event_now_ms() if timestamp is None else timestamp,
        "data": dict(data),
    }
    if source_event_seqs is not None:
        record["sourceEventSeqs"] = list(source_event_seqs)
    if surface_op is not None:
        record["surfaceOp"] = surface_op
    return SessionEvent.from_record(record)


def validate_contiguous_events(
    events: Iterable[SessionEvent], *, start_seq: int = 0
) -> list[SessionEvent]:
    materialized = list(events)
    by_seq: dict[int, SessionEvent] = {}
    for index, event in enumerate(materialized):
        expected = start_seq + index
        if event.seq != expected:
            raise SessionEventCorruptionError(
                f"session event seq gap: expected {expected}, got {event.seq}"
            )
        # Round-trip validation also catches values mutated through unsafe aliases.
        SessionEvent.from_record(event.to_record())
        if event.type == "compaction/checkpoint":
            for source_seq in event.source_event_seqs or ():
                # Incremental readers/appends may not include the earlier prefix.
                # Validate its references when the complete log is available.
                if source_seq < start_seq:
                    continue
                source = by_seq.get(source_seq)
                if source is None or source.type not in (
                    SURFACE_EVENT_TYPES | {"harness/observation"}
                ):
                    raise SessionEventCorruptionError(
                        "compaction/checkpoint sources must reference model message events"
                    )
        if event.type == "tool/result" and isinstance(event.surface_op, dict):
            source_seq = event.source_event_seqs[0]
            if source_seq >= start_seq:
                source = by_seq[source_seq]
                error = source.data.get("error")
                if (
                    source.type != "tool/result"
                    or source.data.get("status") != "interrupted"
                    or source.data.get("result") is not None
                    or not isinstance(error, dict)
                    or error.get("code") != "TOOL_OUTCOME_UNKNOWN"
                    or any(
                        source.data.get(field) != event.data.get(field)
                        for field in ("turn_id", "call_id", "tool_call_id", "name")
                    )
                ):
                    raise SessionEventCorruptionError(
                        "tool/result replacement must resolve the same interrupted unknown call"
                    )
        by_seq[event.seq] = event
    return materialized


def assert_json_value(value: Any, *, label: str = "value") -> None:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise SessionEventError(f"{label} must be losslessly JSON-serializable") from exc


def iso_to_epoch_ms(value: Any, *, fallback: int | None = None) -> int:
    from backend.app.core.time import parse_local_datetime

    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    if isinstance(value, str) and value:
        try:
            parsed = parse_local_datetime(value)
            return int(parsed.timestamp() * 1000)
        except ValueError:
            pass
    return event_now_ms() if fallback is None else fallback




def _validate_surface_op(value: Any) -> None:
    if value == "append":
        return
    if not isinstance(value, dict) or set(value) != {"op", "start", "end"}:
        raise SessionEventCorruptionError("surfaceOp must be append or a replace range")
    if value.get("op") != "replace":
        raise SessionEventCorruptionError("surfaceOp replacement op must be replace")
    start = value.get("start")
    end = value.get("end")
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or start < 0
        or end <= start
    ):
        raise SessionEventCorruptionError("surfaceOp replacement range is invalid")
