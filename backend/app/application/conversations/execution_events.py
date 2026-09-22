"""Persist Harness actions and publish workflow progress for one conversation turn."""

from typing import Any
from backend.app.core.time import local_now_iso


class ConversationExecutionEvents:
    """Own the current tool parent and the ordering of tool audit and cancellation."""

    def __init__(
        self,
        *,
        repository,
        events,
        tool_results,
        account_id,
        turn,
        user_message,
        model,
        check,
        on_workflow_event,
        cancellation_token,
    ):
        self.repository, self.events, self.tool_results = (
            repository,
            events,
            tool_results,
        )
        self.account_id, self.turn, self.user_message = (account_id, turn, user_message)
        self.model, self.check, self.on_workflow_event = (
            model,
            check,
            on_workflow_event,
        )
        self.cancellation_token = cancellation_token
        self.parent_call = {"value": None}

    def append_model_surface(
        self,
        *,
        role: str,
        content: Any,
        message_id: str,
        tool_calls: list[dict[str, Any]] | None = None,
        pagination: dict[str, Any] | None = None,
    ) -> None:
        self.check()
        event_type = "assistant/message" if role == "assistant" else "user/message"
        data = {
            "turn_id": self.turn["turn_id"],
            "message_id": message_id,
            "parent_message_id": self.user_message["message_id"],
            "model_id": self.model()["model_id"],
            "branch_addressable": False,
            "status": "completed",
            "content": content,
            "created_at": local_now_iso(),
        }
        if tool_calls is not None:
            data["tool_calls"] = tool_calls
        if pagination is not None:
            data.update(origin="harness_pagination", pagination=pagination)
        self.repository.append_session_event(
            self.account_id,
            self.turn["session_id"],
            event_type,
            data,
            surface_op="append",
        )

    def handle(self, event) -> None:
        payload = dict(getattr(event, "payload", {}) or {})
        if event.type in {"tool_result", "tool_error"}:
            persisted = self.tool_results.persist(
                self.account_id,
                self.turn,
                payload,
                failed=event.type == "tool_error",
                cancellation_token=self.cancellation_token,
            )
            self.check()
            if not persisted:
                return
        else:
            self.check()
        if event.type == "assistant_tool_calls":
            calls = list(payload.get("tool_calls") or [])
            self.append_model_surface(
                role="assistant",
                content=payload.get("content"),
                message_id="assistant_tools_"
                + str(calls[0].get("id") if calls else self.repository.new_id()),
                tool_calls=calls,
                pagination=payload.get("pagination"),
            )
            return
        if event.type == "assistant_intermediate":
            self.append_model_surface(
                role="assistant",
                content=payload.get("content", ""),
                message_id=f"assistant_internal_{self.repository.new_id()}",
            )
            return
        if event.type == "harness_observation":
            step = self.events.current_model_step(self.account_id, self.turn)
            self.repository.append_session_event(
                self.account_id,
                self.turn["session_id"],
                "harness/observation",
                {
                    "turn_id": self.turn["turn_id"],
                    "step": step,
                    "call_id": self.parent_call["value"],
                    "observation": payload,
                    "status": "failed" if payload.get("error") else "completed",
                    "created_at": local_now_iso(),
                },
            )
            return
        if event.type == "tool_call":
            tool_name = str(payload.get("tool") or "")
            call_id = str(payload.get("call_id") or "")
            self.parent_call["value"] = str(
                payload.get("tool_call_id") or payload.get("call_id") or ""
            )
            self.repository.append_session_event(
                self.account_id,
                self.turn["session_id"],
                "tool/call",
                {
                    "turn_id": self.turn["turn_id"],
                    "step": self.events.current_model_step(self.account_id, self.turn),
                    "call_id": str(payload.get("call_id")),
                    "tool_call_id": str(payload.get("tool_call_id")),
                    "name": tool_name,
                    "arguments": payload.get("arguments", {}),
                    **(
                        {
                            "origin": "harness_pagination",
                            "pagination": payload["pagination"],
                        }
                        if payload.get("pagination")
                        else {}
                    ),
                    "created_at": local_now_iso(),
                },
            )
            self.on_workflow_event(
                {
                    "stage": "tool",
                    "status": "started",
                    "label": tool_name,
                    "detail": "正在执行工具调用",
                    "_persisted_call_id": payload.get("call_id"),
                    "_tool_call_id": payload.get("tool_call_id"),
                    "_step": self.events.current_model_step(self.account_id, self.turn),
                    "_tool_name": tool_name,
                    "_raw_input": payload.get("arguments"),
                }
            )
            return
        if event.type in {"tool_result", "tool_error"}:
            tool_name = str(payload.get("tool") or "")
            failed = event.type == "tool_error"
            call_id = str(payload.get("call_id") or "")
            self.on_workflow_event(
                {
                    "stage": "tool",
                    "status": "failed" if failed else "completed",
                    "label": tool_name,
                    "detail": "工具调用失败，结果已返回 Agent"
                    if failed
                    else "工具调用已完成",
                    "_persisted_call_id": payload.get("call_id"),
                    "_tool_call_id": payload.get("tool_call_id"),
                    "_step": self.events.current_model_step(self.account_id, self.turn),
                    "_tool_name": tool_name,
                    "_raw_output": None if failed else payload.get("output"),
                    **({"_raw_error": payload.get("error")} if failed else {}),
                }
            )
            self.parent_call["value"] = None
