"""保存和调整等待输入，通过明确回调创建轮次、启动执行或取消当前轮次。"""

from backend.app.core.member_lifecycle import (
    member_lifecycle_operation,
    member_lifecycle_guard,
)
from typing import Any, Callable, Protocol
from backend.app.repositories.member_repository import MemberAccess


from backend.app.core.errors import raise_error
from backend.app.domain.conversations.queries import queued_inputs_from_events
from backend.app.core.time import local_now_iso
from backend.app.domain.conversations.events import SessionEvent, iso_to_epoch_ms
from backend.app.storage.session_persistence import SessionEventWriteConflictError


from dataclasses import dataclass

now_iso = local_now_iso


class StartMessageTurn(Protocol):
    def __call__(
        self,
        *,
        account_id: str,
        session_id: str,
        raw_text: str,
        model_id: str,
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
        attach_resources: bool,
        current_events: list[SessionEvent],
        expected_seq: int,
        queued_input_id: str | None = None,
    ) -> dict[str, Any]: ...


class CancelTurn(Protocol):
    def __call__(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        preserve_partial: bool = True,
        *,
        reason: str = "cancelled",
    ) -> dict[str, Any]: ...


@dataclass(frozen=True)
class ConversationQueueActions:
    member_accessible: Callable[[str, str], bool]
    start_message: StartMessageTurn
    start_job: Callable[[str, str, str], None]
    cancel_turn: CancelTurn
    get_turn: Callable[[str, str, str], dict[str, Any]]
    member_access: Callable[[str, str], MemberAccess | None]
    current_records: Callable[[str, str], list[dict[str, Any]]]
    drain_cleanup: Callable[[str], None]


class ConversationQueue:
    def __init__(
        self, repository, paths, members, task_state, actions: ConversationQueueActions
    ):
        self.repository = repository
        self.paths = paths
        self.members = members
        self.task_state = task_state
        self.actions = actions

    def enqueue(
        self,
        *,
        account_id: str,
        session_id: str,
        raw_text: str,
        model_id: str,
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        input_id = self.repository.new_id()
        timestamp = now_iso()
        queued_input = {
            "input_id": input_id,
            "content": raw_text,
            "model_id": model_id,
            "thinking_mode": thinking_mode,
            "context_resources": context_resources,
            "created_at": timestamp,
        }
        self.repository.append_session_events(
            account_id,
            session_id,
            [
                {
                    "type": "input/queued",
                    "timestamp": iso_to_epoch_ms(timestamp),
                    "data": queued_input,
                }
            ],
        )
        self.repository.attach_file_resources(account_id, session_id, context_resources)
        self.repository.touch_session(account_id, session_id)
        queued_inputs = self.inputs(account_id, session_id)
        return {
            "disposition": "queued",
            "member_id": self.repository.session_row(account_id, session_id)[
                "member_id"
            ],
            "member_name": self.members.historical_member_name(
                account_id, "conversation", session_id
            ),
            "session_id": session_id,
            "title": self.repository.session_row(account_id, session_id)["title"],
            "queued_input": next(
                item for item in queued_inputs if item["input_id"] == input_id
            ),
            "queued_inputs": queued_inputs,
        }

    def inputs(self, account_id: str, session_id: str) -> list[dict[str, Any]]:
        return queued_inputs_from_events(
            self.repository.session_events(account_id, session_id, repair=False)
        )

    def reorder(
        self, account_id: str, session_id: str, input_ids: list[str]
    ) -> dict[str, Any]:
        self.repository.ensure_session(account_id, session_id)
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            current = self.inputs(account_id, session_id)
            current_ids = [str(item["input_id"]) for item in current]
            normalized = [str(input_id) for input_id in input_ids]
            if len(normalized) != len(set(normalized)) or set(normalized) != set(
                current_ids
            ):
                raise_error(
                    "conflict",
                    "QUEUE_CONFLICT",
                    "等候队列已经变化，请刷新后重试。",
                )
            self.repository.append_session_events(
                account_id,
                session_id,
                [
                    {
                        "type": "input/queue-reordered",
                        "data": {"input_ids": normalized},
                    }
                ],
            )
            return {
                "session_id": session_id,
                "queued_inputs": self.inputs(account_id, session_id),
            }

    def remove(
        self,
        account_id: str,
        session_id: str,
        input_id: str,
        *,
        restore_to_draft: bool = False,
    ) -> dict[str, Any]:
        self.repository.ensure_session(account_id, session_id)
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            current = self.inputs(account_id, session_id)
            target = next(
                (item for item in current if item["input_id"] == input_id), None
            )
            if target is None:
                raise_error(
                    "conflict",
                    "QUEUE_CONFLICT",
                    "该输入已不在等候队列中。",
                )
            self.repository.append_session_events(
                account_id,
                session_id,
                [
                    {
                        "type": "input/queue-removed",
                        "data": {
                            "input_id": input_id,
                            "reason": "restored_to_draft"
                            if restore_to_draft
                            else "deleted",
                        },
                    }
                ],
            )
            remaining = self.inputs(account_id, session_id)
            if not restore_to_draft:
                self.cleanup_removed_resources(
                    account_id, session_id, target, remaining
                )
            return {
                "session_id": session_id,
                "queued_input": target,
                "queued_inputs": remaining,
            }

    @member_lifecycle_operation
    def run_now(
        self, account_id: str, session_id: str, input_id: str
    ) -> dict[str, Any]:
        self.actions.member_access(account_id, session_id)
        self.repository.ensure_session(account_id, session_id)
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            current = self.inputs(account_id, session_id)
            if not any(item["input_id"] == input_id for item in current):
                raise_error(
                    "conflict",
                    "QUEUE_CONFLICT",
                    "该输入已不在等候队列中。",
                )
            ordered_ids = [input_id] + [
                str(item["input_id"])
                for item in current
                if item["input_id"] != input_id
            ]
            self.repository.append_session_events(
                account_id,
                session_id,
                [
                    {
                        "type": "input/queue-reordered",
                        "data": {"input_ids": ordered_ids},
                    }
                ],
            )
            pending = self.repository.list_pending_turn_rows(account_id, session_id)
            if pending:
                self.actions.cancel_turn(
                    account_id,
                    session_id,
                    str(pending[0]["turn_id"]),
                    preserve_partial=True,
                    reason="steered",
                )
            else:
                self.promote_next(account_id, session_id)
            active = self.repository.list_pending_turn_rows(account_id, session_id)
            return {
                "session_id": session_id,
                "started_turn": (
                    self.actions.get_turn(
                        account_id, session_id, str(active[0]["turn_id"])
                    )
                    if active
                    else None
                ),
                "queued_inputs": self.inputs(account_id, session_id),
            }

    @member_lifecycle_operation
    def promote_next(self, account_id: str, session_id: str) -> dict[str, Any] | None:
        if not self.actions.member_accessible(account_id, session_id):
            return None
        with (
            member_lifecycle_guard(paths=self.paths),
            self.task_state.session_lock(account_id, session_id),
        ):
            for _attempt in range(128):
                if self.repository.session_row(account_id, session_id) is None:
                    return None
                events = self.repository.session_events(
                    account_id,
                    session_id,
                    repair=False,
                )
                self.repository.reconcile_session_indexes(
                    account_id,
                    session_id,
                    events=events,
                )
                if self.repository.list_pending_turn_rows(account_id, session_id):
                    return None
                queued_inputs = queued_inputs_from_events(events)
                if not queued_inputs:
                    return None
                target = queued_inputs[0]
                try:
                    response = self.actions.start_message(
                        account_id=account_id,
                        session_id=session_id,
                        raw_text=str(target.get("content") or ""),
                        model_id=str(target.get("model_id") or ""),
                        thinking_mode=str(target.get("thinking_mode") or "default"),
                        context_resources=list(target.get("context_resources") or []),
                        attach_resources=False,
                        current_events=events,
                        expected_seq=len(events),
                        queued_input_id=str(target["input_id"]),
                    )
                except SessionEventWriteConflictError:
                    continue
                self.actions.start_job(
                    account_id, session_id, str(response["stream_id"])
                )
                return response
            return None

    def cleanup_removed_resources(
        self,
        account_id: str,
        session_id: str,
        removed: dict[str, Any],
        remaining: list[dict[str, Any]],
    ) -> None:
        # Restoring transfers ownership to the draft. Another queued reference
        # being deleted must not invalidate that draft's attachment.
        queued_files: dict[str, set[str]] = {}
        draft_files: set[str] = set()
        for event in self.repository.session_events(
            account_id, session_id, repair=False
        ):
            if event.type in {"input/queued", "user/message"}:
                files = {
                    str(resource.get("resource_id") or "")
                    for resource in event.data.get("context_resources") or []
                    if resource.get("resource_type") == "file"
                }
                draft_files.difference_update(files)
                if event.type == "input/queued":
                    queued_files[str(event.data.get("input_id"))] = files
            elif event.type == "input/queue-removed":
                files = queued_files.pop(str(event.data.get("input_id")), set())
                if event.data.get("reason") == "restored_to_draft":
                    draft_files.update(files)
        live_resource_ids = {
            str(resource.get("resource_id") or "")
            for record in self.actions.current_records(account_id, session_id)
            if record.get("kind") == "user"
            for resource in record.get("context_resources") or []
            if resource.get("resource_type") == "file"
        }
        live_resource_ids.update(
            str(resource.get("resource_id") or "")
            for item in remaining
            for resource in item.get("context_resources") or []
            if resource.get("resource_type") == "file"
        )
        live_resource_ids.update(draft_files)
        for resource in removed.get("context_resources") or []:
            resource_id = str(resource.get("resource_id") or "")
            if (
                resource.get("resource_type") == "file"
                and resource_id not in live_resource_ids
            ):
                self.repository.expire_resource(account_id, session_id, resource_id)
        self.actions.drain_cleanup(account_id)
