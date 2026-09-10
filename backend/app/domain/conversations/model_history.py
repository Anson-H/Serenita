"""从会话事件派生模型消息和已读取技能，处理压缩与工具结果替换。"""

from __future__ import annotations
import json
from typing import Any, Iterable
from backend.app.domain.conversations.events import SessionEvent

from backend.app.domain.conversations.queries import current_session_turn_ids


def tool_result_is_model_visible(data: dict[str, Any]) -> bool:
    """Execution audit alone never authorizes exposing a failed result."""
    return data.get("status") == "completed"


def derive_model_messages(
    events: Iterable[SessionEvent],
    *,
    current_turn_ids: Iterable[str] = (),
    include_user_context: bool = False,
    include_surface_metadata: bool = False,
) -> list[dict[str, Any]]:
    """Derive the current linear model surface from one session log.

    ``include_user_context`` preserves private projection metadata long enough
    for the conversation service to restore each attachment to the exact user
    message that originally carried it. Provider-facing callers keep the
    default, metadata-free projection.

    ``include_surface_metadata`` exposes each message's original event seq,
    projected position and owning turn for precise compaction selection.
    Unknown interrupted tool outcomes also carry ``_pending_execution=True``
    so selection can keep their entire protocol group until execution settles.
    Checkpoints consume only their explicit sources on the current branch;
    their replacement range controls placement, never message deletion.
    """

    materialized = list(events)
    active_turns = current_session_turn_ids(materialized)
    active_turns.update(str(turn_id) for turn_id in current_turn_ids if str(turn_id))
    active_user_ids = {
        str(event.data.get("user_message_id") or "")
        for event in materialized
        if event.type == "turn/start"
        and str(event.data.get("turn_id") or "") in active_turns
    }
    active_user_ids.update(
        str(event.data.get("message_id") or "")
        for event in materialized
        if event.type == "user/message"
        and str(event.data.get("turn_id") or "") in active_turns
    )
    message_patches: dict[str, dict[str, Any]] = {}
    for event in materialized:
        if event.type not in {"user/message-update", "assistant/message-update"}:
            continue
        message_id = str(event.data.get("message_id") or "")
        patch = event.data.get("patch")
        if message_id and isinstance(patch, dict):
            message_patches.setdefault(message_id, {}).update(patch)
    # Late completion replaces an interrupted placeholder at its original
    # position. Use the new source seq so checkpoints based on the unknown
    # outcome are invalidated, including summaries of those checkpoints.
    by_seq = {event.seq: event for event in materialized}
    tool_replacements: dict[int, SessionEvent] = {}
    replacement_seqs: set[int] = set()
    for event in materialized:
        if event.type != "tool/result" or not isinstance(event.surface_op, dict):
            continue
        # A replacement never appends a second native tool result. Invalid or
        # unavailable sources are left untouched rather than becoming orphans.
        replacement_seqs.add(event.seq)
        sources = event.source_event_seqs or ()
        previous = by_seq.get(sources[0]) if len(sources) == 1 else None
        if (
            previous is not None
            and previous.type == "tool/result"
            and previous.data.get("status") == "interrupted"
            and previous.data.get("result") is None
            and (previous.data.get("error") or {}).get("code") == "TOOL_OUTCOME_UNKNOWN"
            and event.surface_op
            == {"op": "replace", "start": previous.seq, "end": previous.seq + 1}
            and all(
                event.data.get(key) == previous.data.get(key)
                for key in ("turn_id", "call_id", "tool_call_id", "name")
            )
        ):
            tool_replacements[previous.seq] = event
    messages: dict[int, dict[str, Any]] = {}
    for event in materialized:
        if event.seq in replacement_seqs:
            continue
        surface_seq = event.seq
        event = tool_replacements.get(event.seq, event)
        data = event.data
        turn_id = str(data.get("turn_id") or "")
        if event.type == "user/message":
            projected_data = {
                **data,
                **message_patches.get(str(data.get("message_id") or ""), {}),
            }
            branch_addressable = data.get("branch_addressable") is not False
            if (
                branch_addressable
                and str(data.get("message_id") or "") not in active_user_ids
            ):
                continue
            if not branch_addressable and turn_id not in active_turns:
                continue
            messages[event.seq] = {
                "role": "user",
                "content": projected_data.get("content", ""),
                "message_id": data.get("message_id"),
                "_context_resources": list(
                    projected_data.get("context_resources") or []
                ),
                "turn_id": turn_id,
                "_surface_seq": event.seq,
            }
            continue
        if event.type == "assistant/message":
            projected_data = {
                **data,
                **message_patches.get(str(data.get("message_id") or ""), {}),
            }
            branch_addressable = data.get("branch_addressable") is not False
            if branch_addressable:
                if turn_id not in active_turns:
                    continue
            elif turn_id not in active_turns:
                continue
            message: dict[str, Any] = {
                "role": "assistant",
                "content": projected_data.get("content"),
                "message_id": data.get("message_id"),
                "turn_id": turn_id,
                "_surface_seq": event.seq,
            }
            if isinstance(projected_data.get("tool_calls"), list):
                message["tool_calls"] = list(projected_data["tool_calls"])
            messages[event.seq] = message
            continue
        if event.type == "tool/result" and turn_id in active_turns:
            result = (
                {"error": data.get("error")}
                if not tool_result_is_model_visible(data)
                else data.get("result")
            )
            messages[event.seq] = {
                "role": "tool",
                "tool_call_id": data.get("tool_call_id"),
                "name": data.get("name"),
                "content": (
                    result
                    if isinstance(result, str)
                    else json.dumps(
                        result,
                        ensure_ascii=False,
                        separators=(",", ":"),
                        default=str,
                    )
                ),
                "turn_id": turn_id,
                "_surface_seq": surface_seq,
            }
            continue
        if event.type == "harness/observation" and turn_id in active_turns:
            messages[event.seq] = {
                "role": "user",
                "content": "HARNESS_OBSERVATION\n"
                + json.dumps(
                    data.get("observation") or {},
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ),
                "turn_id": turn_id,
                "_surface_seq": event.seq,
            }
            continue
        if event.type == "compaction/checkpoint":
            operation = event.surface_op
            if not isinstance(operation, dict) or operation.get("op") != "replace":
                continue
            sources = event.source_event_seqs
            # A summary is indivisible: if any of its inputs disappeared after
            # an edit/retry (including an older summary), none of it is safe to
            # reuse. Replaying against the active branch restores the remaining
            # original messages without changing the durable execution log.
            if (
                turn_id in active_turns
                and sources
                and all(source in messages for source in sources)
            ):
                for source in sources:
                    del messages[source]
                messages[event.seq] = {
                    "role": "user",
                    "content": data.get("content", ""),
                    "message_id": data.get("message_id"),
                    "turn_id": turn_id,
                    "_surface_seq": int(operation["start"]),
                }
    projected_messages: list[dict[str, Any]] = []
    for source_seq, message in sorted(
        messages.items(), key=lambda item: (item[1]["_surface_seq"], item[0])
    ):
        projected = {
            key: value
            for key, value in message.items()
            if key
            not in {
                "message_id",
                "turn_id",
                "_surface_seq",
                "_context_resources",
            }
        }
        if include_user_context and message.get("role") == "user":
            message_id = str(message.get("message_id") or "")
            if message_id:
                projected["_message_id"] = message_id
                projected["_context_resources"] = list(
                    message.get("_context_resources") or []
                )
        if include_surface_metadata:
            projected.update(
                _source_seq=source_seq,
                _surface_seq=message["_surface_seq"],
                _turn_id=message["turn_id"],
            )
            source = by_seq[source_seq]
            error = source.data.get("error")
            if (
                source.type == "tool/result"
                and source.data.get("status") == "interrupted"
                and isinstance(error, dict)
                and error.get("code") == "TOOL_OUTCOME_UNKNOWN"
            ):
                projected["_pending_execution"] = True
        projected_messages.append(projected)
    return projected_messages


def visible_loaded_skill_names(
    events: Iterable[SessionEvent],
    *,
    current_turn_ids: Iterable[str] = (),
) -> list[str]:
    """Return successful, still-visible ``load_skill`` names for one branch.

    A Skill carries over to the next Turn only while its real ``load_skill``
    Tool Observation remains part of the active model surface. Compaction,
    failed reads, and inactive branches therefore do not restore Tool access.
    """

    materialized = list(events)
    visible_result_call_ids = {
        str(message.get("tool_call_id") or "")
        for message in derive_model_messages(
            materialized,
            current_turn_ids=current_turn_ids,
        )
        if message.get("role") == "tool"
        and message.get("name") == "load_skill"
        and message.get("tool_call_id")
    }
    if not visible_result_call_ids:
        return []

    completed_result_seqs: dict[str, int] = {}
    for event in materialized:
        if event.type != "tool/result":
            continue
        call_id = str(event.data.get("call_id") or "")
        if call_id not in visible_result_call_ids:
            continue
        if event.data.get("name") != "load_skill":
            continue
        if event.data.get("status") != "completed":
            continue
        result = event.data.get("result")
        if not isinstance(result, str) or not result.strip():
            continue
        completed_result_seqs[call_id] = event.seq
    if not completed_result_seqs:
        return []

    skill_names: dict[str, str] = {}
    for event in materialized:
        if event.type != "tool/call":
            continue
        call_id = str(event.data.get("call_id") or "")
        if call_id not in completed_result_seqs:
            continue
        if event.data.get("name") != "load_skill":
            continue
        arguments = event.data.get("arguments")
        skill_name = (
            str(arguments.get("name") or "").strip()
            if isinstance(arguments, dict)
            else ""
        )
        if skill_name:
            skill_names[call_id] = skill_name

    restored: list[str] = []
    seen: set[str] = set()
    for call_id, _seq in sorted(
        completed_result_seqs.items(), key=lambda item: (item[1], item[0])
    ):
        skill_name = skill_names.get(call_id)
        if not skill_name or skill_name in seen:
            continue
        seen.add(skill_name)
        restored.append(skill_name)
    return restored
