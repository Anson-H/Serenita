"""查询账号可访问的会话、轮次和关联资源，准备详情与目录数据。"""

from backend.app.application.conversations.access import session_member_access
from typing import Any, Optional
from backend.app.core.errors import SerenitaError
from backend.app.core.errors import raise_error
from backend.app.application.conversations.presenter import record_response, message_response
from backend.app.domain.conversations.queries import current_session_turn_ids
from backend.app.plugins.web.citations import export_web_citation_markdown

class ConversationQueries:
    def __init__(self, *, repository, members, events, services):
        self.repository = repository
        self.members = members
        self.events = events
        self.services = services

    def session_binding(self, account_id: str, session_id: str) -> dict[str, Any]:
        row = self.repository.session_row(account_id, session_id)
        if row is None:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        return {"session_id": session_id, "member_id": row["member_id"]}


    def member_access(self, account_id: str, session_id: str):
        return session_member_access(
            self.repository, self.members, account_id, session_id
        )


    def member_accessible(self, account_id: str, session_id: str) -> bool:
        try:
            self.member_access(account_id, session_id)
            return True
        except SerenitaError as exc:
            if exc.kind in {"forbidden", "missing"}:
                return False
            raise


    def get_turn(
        self, account_id: str, session_id: str, turn_id: str
    ) -> dict[str, Any]:
        self.repository.ensure_session(account_id, session_id)
        row = self.repository.turn_row(account_id, session_id, turn_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "轮次不存在。")
        return {
            "session_id": row["session_id"],
            "turn_id": row["turn_id"],
            "status": row["status"],
            "stream_id": row["stream_id"],
            "user_message_id": row["user_message_id"],
            "final_assistant_message_id": row["final_assistant_message_id"],
            "error": None
            if not row["error_code"]
            else {"code": row["error_code"], "message": row["error_message"]},
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }


    def list_conversations(
        self, account_id: str, *, cursor=None, limit=24
    ) -> dict[str, Any]:
        rows, next_cursor = self.repository.list_sessions(
            account_id, cursor=cursor, limit=limit
        )
        summaries = [self.summary(account_id, row) for row in rows]
        return {
            "sessions": summaries,
            "has_more": next_cursor is not None,
            "next_cursor": next_cursor,
        }


    def get_conversation(self, account_id: str, session_id: str) -> dict[str, Any]:
        row = self.repository.session_row(account_id, session_id)
        if not row:
            raise_error("missing", "NOT_FOUND", "聊天不存在。")
        view = self.events.view(account_id, session_id)
        events = view.events
        self.repository.reconcile_session_indexes(account_id, session_id, events=events)
        row = self.repository.session_row(account_id, session_id)
        current_records = view.records
        fork_anchor_seqs = self._fork_anchor_seqs(current_records, events)
        latest = self.latest_turn(account_id, session_id, events=events)
        member_accessible = self.member_accessible(account_id, session_id)
        latest_terminal = (
            member_accessible
            and latest is not None
            and latest["status"]
            not in {
                "queued",
                "streaming",
            }
        )
        records = [
            self._conversation_record_response(
                record,
                editable=(
                    latest_terminal
                    and record.get("kind") == "user"
                    and str(record.get("message_id") or record.get("record_id") or "")
                    == str(latest["user_message_id"] or "")
                ),
                regenerable=(
                    latest_terminal
                    and record.get("kind") == "assistant"
                    and str(record.get("message_id") or record.get("record_id") or "")
                    == str(latest["final_assistant_message_id"] or "")
                ),
                fork_anchor_seq=fork_anchor_seqs.get(
                    str(record.get("record_id") or record.get("message_id") or "")
                ),
            )
            for record in current_records
        ]
        pending_rows = self.repository.list_pending_turn_rows(account_id, session_id)
        return {
            "session_id": row["session_id"],
            "title": row["title"],
            "parent_session_id": row["parent_session_id"],
            "seed_event_count": int(row["seed_event_count"] or 0),
            "fork_available": member_accessible and self._fork_available(events),
            "member_id": row["member_id"],
            "member_name": self.members.historical_member_name(
                account_id, "conversation", row["session_id"]
            ),
            "access_state": "available" if member_accessible else "history_only",
            "pending_turns": [
                {
                    "turn_id": pending["turn_id"],
                    "status": pending["status"],
                    "stream_id": pending["stream_id"],
                    "user_message_id": pending["user_message_id"],
                    "final_assistant_message_id": pending["final_assistant_message_id"],
                    "created_at": pending["created_at"],
                    "updated_at": pending["updated_at"],
                }
                for pending in pending_rows
            ],
            "queued_inputs": view.queued,
            "records": records,
            "resource_states": self._conversation_resource_states(
                account_id, row["member_id"], current_records
            ),
        }


    def _conversation_resource_states(
        self, account_id: str, member_id: str | None, records: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        resource_refs: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()

        def append_references(value: Any) -> None:
            if not isinstance(value, list):
                return
            for reference in value:
                if not isinstance(reference, dict):
                    continue
                resource_type = str(reference.get("resource_type") or "").strip()
                resource_id = str(reference.get("resource_id") or "").strip()
                key = (
                    str(reference.get("member_id") or ""),
                    resource_type,
                    resource_id,
                )
                if not resource_type or not resource_id or key in seen:
                    continue
                seen.add(key)
                resource_refs.append(
                    {
                        "resource_type": resource_type,
                        "resource_id": resource_id,
                        "member_id": reference.get("member_id"),
                    }
                )

        for record in records:
            if record.get("kind") == "user":
                append_references(record.get("context_resources"))
                continue
            if record.get("kind") != "tool":
                continue
            result = record.get("result")
            effects = result.get("effects") if isinstance(result, dict) else None
            if not isinstance(effects, dict):
                continue
            append_references(effects.get("resource_refs"))
            append_references(effects.get("affected_resource_refs"))

        if not resource_refs:
            return []
        from backend.app.plugins import (
            PluginRuntimeContext,
            resolve_plugin_resource_states,
        )

        return resolve_plugin_resource_states(
            runtime_context=PluginRuntimeContext(
                service_factory=lambda plugin_id: self.services.plugin_service(
                    account_id, member_id, plugin_id
                ),
                account_id=account_id,
                member_id=member_id,
                event_recorder=lambda _event: None,
            ),
            resource_refs=resource_refs,
        )


    def _conversation_record_response(
        self,
        record: dict[str, Any],
        *,
        editable: bool = False,
        regenerable: bool = False,
        fork_anchor_seq: Optional[int] = None,
    ) -> dict[str, Any]:
        if record.get("kind") not in {"user", "assistant"}:
            return record_response(record)
        message = {**record, "role": record["kind"]}
        response = message_response(message)
        return {
            **response,
            "record_id": record["record_id"],
            "kind": record["kind"],
            "time": record.get("time"),
            "source_event_seqs": list(record.get("source_event_seqs") or []),
            **({"editable": editable} if record.get("kind") == "user" else {}),
            **(
                {
                    "regenerable": regenerable,
                    "fork_anchor_seq": fork_anchor_seq,
                }
                if record.get("kind") == "assistant"
                else {}
            ),
        }


    def current_records(
        self, account_id: str, session_id: str
    ) -> list[dict[str, Any]]:
        return self.events.view(account_id, session_id).records


    def latest_turn(
        self,
        account_id: str,
        session_id: str,
        *,
        events: Optional[list[Any]] = None,
    ):
        event_list = (
            events
            if events is not None
            else list(self.events.view(account_id, session_id).events)
        )
        current_ids = current_session_turn_ids(event_list)
        latest_id = next(
            (
                str(event.data.get("turn_id") or "")
                for event in reversed(event_list)
                if event.type == "turn/start"
                and str(event.data.get("turn_id") or "") in current_ids
            ),
            "",
        )
        return (
            self.repository.turn_row(account_id, session_id, latest_id)
            if latest_id
            else None
        )


    def summary(self, account_id: str, row) -> dict[str, Any]:
        view = self.events.view(account_id, str(row["session_id"]))
        row_keys = set(row.keys())
        pending_turn_status = (
            row["pending_turn_status"]
            if "pending_turn_status" in row_keys
            else self.repository.pending_turn_status(account_id, str(row["session_id"]))
        )
        member_accessible = self.member_accessible(account_id, str(row["session_id"]))
        return {
            "session_id": row["session_id"],
            "title": row["title"],
            "member_id": row["member_id"],
            "member_name": self.members.historical_member_name(
                account_id, "conversation", row["session_id"]
            ),
            "access_state": "available" if member_accessible else "history_only",
            "created_at": row["created_at"],
            "last_active_at": row["last_active_at"],
            "parent_session_id": row["parent_session_id"],
            "seed_event_count": int(row["seed_event_count"] or 0),
            "is_pinned": bool(row["is_pinned"]),
            "pending_turn_status": pending_turn_status,
            "queued_input_count": len(view.queued),
            "fork_available": member_accessible and view.fork_available,
        }


    @staticmethod
    def _fork_available(events: list[Any]) -> bool:
        return any(event.type == "turn/end" for event in events)


    @staticmethod
    def _fork_anchor_seq(record: dict[str, Any], events: list[Any]) -> Optional[int]:
        record_id = str(record.get("record_id") or record.get("message_id") or "")
        return ConversationQueries._fork_anchor_seqs([record], events).get(record_id)


    @staticmethod
    def _fork_anchor_seqs(
        records: list[dict[str, Any]], events: list[Any]
    ) -> dict[str, int]:
        previous_event_seq_by_turn: dict[str, int] = {}
        stable_anchors: set[tuple[str, int]] = set()
        for event in events:
            turn_id = str(event.data.get("turn_id") or "")
            if not turn_id:
                continue
            previous_seq = previous_event_seq_by_turn.get(turn_id)
            if event.type == "turn/end" and previous_seq is not None:
                stable_anchors.add((turn_id, previous_seq))
            previous_event_seq_by_turn[turn_id] = event.seq

        anchors: dict[str, int] = {}
        for record in records:
            if record.get("kind") != "assistant":
                continue
            record_id = str(record.get("record_id") or record.get("message_id") or "")
            if not record_id:
                continue
            turn_id = str(record.get("turn_id") or "")
            anchor_seq = max(
                [
                    int(record.get("seq") or -1),
                    *(int(value) for value in record.get("source_event_seqs") or []),
                ]
            )
            if (turn_id, anchor_seq) in stable_anchors:
                anchors[record_id] = anchor_seq
        return anchors


    def source_message_for_favorite(
        self, account_id: str, session_id: str, message_id: str
    ):
        source = self.repository.source_message_for_favorite(
            account_id, session_id, message_id
        )
        if source is None:
            return None
        turn_id = str(source.pop("_turn_id", ""))
        source["content"] = export_web_citation_markdown(
            str(source.get("content") or ""),
            list(self.events.view(account_id, session_id).events),
            turn_id,
        )
        return source


    def conversation_exists(self, account_id: str, session_id: str) -> bool:
        return self.repository.conversation_exists(account_id, session_id)

