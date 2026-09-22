"""Assemble authorized turn inputs and plugin capabilities before Harness execution."""

from dataclasses import dataclass
from copy import deepcopy
import json
from typing import Any, Callable
from backend.app.core.cancellation import CancellationToken
from backend.app.core.time import local_now_iso
from backend.app.agent_runtime.prompts import ATTACHED_ANNOTATION_PREFIX
from backend.app.domain.conversations.model_history import visible_loaded_skill_names
from backend.app.application.conversations.model_input import ConversationModelInput


@dataclass(frozen=True)
class PreparedConversationTurn:
    context: Any
    tools: Any
    model_input: ConversationModelInput
    read_events: Callable
    refresh_member: Callable
    skill_names: list[str]
    thinking_mode: str


class ConversationTurnPreparation:
    def __init__(
        self,
        *,
        repository,
        members,
        paths,
        plugin_service,
        events,
        inputs,
        model_catalog,
        guard,
    ):
        self.repository, self.members, self.paths = (repository, members, paths)
        self.plugin_service, self.events, self.inputs = (plugin_service, events, inputs)
        self.model_catalog, self.guard = (model_catalog, guard)

    def prepare(
        self,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        *,
        on_workflow_event: Callable[[dict[str, Any]], None],
        cancellation_token: CancellationToken | None = None,
    ) -> PreparedConversationTurn:
        self.guard.ensure_active(account_id, turn, cancellation_token)
        from backend.app.agent_runtime.context import AgentContext
        from backend.app.agent_runtime.tools.registry import ToolRegistry
        from backend.app.plugins import (
            PluginRuntimeContext,
            build_available_tools,
            resolve_plugin_input_model_resources,
        )

        session_id = str(turn["session_id"])
        turn_id = str(turn["turn_id"])
        read_events = self.events.reader(account_id, session_id)
        event_view = read_events()
        session_events = event_view.events
        current_message_records = {
            str(record.get("message_id") or record.get("record_id") or ""): {
                **record,
                "role": record.get("kind"),
            }
            for record in event_view.records
            if record.get("kind") in {"user", "assistant"}
        }
        visible_message_ids = {
            str(record.get("message_id") or record.get("record_id") or "")
            for record in current_message_records.values()
        }
        initial_skill_names = visible_loaded_skill_names(
            session_events, current_turn_ids=[turn_id]
        )
        base_decision_model = self.inputs.validate_model(
            account_id,
            user_message.get("model_id"),
            user_message.get("thinking_mode", "default"),
        )
        active_user_message_records = [
            record
            for record in current_message_records.values()
            if record.get("role") == "user"
        ]
        session_file_resources: list[dict[str, Any]] = []
        seen_file_resource_ids: set[str] = set()
        for message_record in active_user_message_records:
            for resource in message_record.get("context_resources", []):
                if not isinstance(resource, dict):
                    continue
                if resource.get("resource_type") != "file":
                    continue
                resource_id = str(resource.get("resource_id") or "")
                if not resource_id or resource_id in seen_file_resource_ids:
                    continue
                seen_file_resource_ids.add(resource_id)
                session_file_resources.append(dict(resource))
        decision_model, session_attachment_parts = (
            self.inputs.model_and_attachment_parts(
                account_id, session_id, session_file_resources, base_decision_model
            )
        )
        attachment_parts_by_resource_id: dict[str, list[dict[str, Any]]] = {}
        for part in session_attachment_parts:
            resource_id = str(part.get("source_resource_id") or "")
            if resource_id:
                attachment_parts_by_resource_id.setdefault(resource_id, []).append(part)

        def resolve_conversation_resource(resource_id: str) -> dict[str, Any] | None:
            return self.inputs.trusted_attachment_resource(
                account_id, session_id, resource_id
            )

        def resolve_message(message_id: str) -> dict[str, Any] | None:
            message = read_events().messages.get(message_id)
            return deepcopy(message) if message is not None else None

        def resolve_tool_observation(
            *, call_id, allowed_tools, session_id, visible_message_ids
        ):
            if session_id != str(turn["session_id"]):
                return None
            return read_events().observation(
                call_id=call_id,
                allowed_tools=allowed_tools,
                session_id=session_id,
                visible_message_ids=visible_message_ids,
            )

        member_access = self.guard.member_access(account_id, session_id)
        member_metadata: dict[str, Any] = {}
        if member_access is not None:
            with member_access.guard() as live:
                member_metadata = self.members.detail(live, self.paths)
        tool_registry = ToolRegistry()
        plugin_runtime_context = PluginRuntimeContext(
            service_factory=lambda plugin_id: self.plugin_service(
                account_id,
                member_access.member_id if member_access else None,
                plugin_id,
            ),
            account_id=account_id,
            member_id=member_access.member_id if member_access is not None else None,
            event_recorder=on_workflow_event,
            observation_resolver=resolve_tool_observation,
            conversation_resource_resolver=resolve_conversation_resource,
            conversation_attachment_reader=lambda resource_id: (
                self.inputs.read_attachment_content(account_id, session_id, resource_id)
            ),
            message_resolver=resolve_message,
            cancellation_token=cancellation_token,
        )
        for tool in build_available_tools(runtime_context=plugin_runtime_context):
            tool_registry.register(tool)
        visible_attachments = self.inputs.visible_attachments_for_messages(
            account_id, session_id, current_message_records, visible_message_ids
        )
        from backend.app.application.conversations.model_resources import (
            ConversationModelResources,
        )

        model_resources = ConversationModelResources(
            account_id=account_id,
            inputs=self.inputs,
            model_catalog=self.model_catalog,
            runtime_context=plugin_runtime_context,
        )
        model_resource_parts = model_resources.prepare
        input_model_resources = resolve_plugin_input_model_resources(
            runtime_context=plugin_runtime_context,
            resource_refs=[
                dict(resource)
                for resource in user_message.get("context_resources", [])
                if isinstance(resource, dict)
            ],
        )
        decision_model, runtime_context_resource_parts = model_resource_parts(
            [], decision_model, resolved_resources=input_model_resources
        )
        annotation_input_parts = [
            {
                "type": "text",
                "text": ATTACHED_ANNOTATION_PREFIX
                + json.dumps(
                    {
                        "resource_id": resource.get("resource_id"),
                        "source_record_id": resource.get("source_record_id"),
                        "annotation_text": resource.get("annotation_text"),
                    },
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "name": "注释",
                "model_resource_ref": {
                    "resource_type": "record_annotation",
                    "resource_id": resource.get("resource_id"),
                    "source_record_id": resource.get("source_record_id"),
                },
            }
            for resource in user_message.get("context_resources", [])
            if isinstance(resource, dict)
            and resource.get("resource_type") == "record_annotation"
        ]
        current_runtime_input_parts = [
            *annotation_input_parts,
            *runtime_context_resource_parts,
        ]
        requested_thinking_mode = self.inputs.thinking_mode_for_model(
            decision_model, str(user_message.get("thinking_mode") or "default")
        )
        effective_thinking_mode, thinking_mode_reasons = (
            self.inputs.effective_thinking_mode_for_turn(
                decision_model,
                requested_thinking_mode,
                has_tools=tool_registry.has_tools(),
                attachment_parts=[
                    *session_attachment_parts,
                    *runtime_context_resource_parts,
                ],
            )
        )
        if effective_thinking_mode != requested_thinking_mode:
            self.repository.append_session_event(
                account_id,
                turn["session_id"],
                "turn/thinking_mode_changed",
                {
                    "turn_id": turn["turn_id"],
                    "requested_mode": requested_thinking_mode,
                    "effective_mode": effective_thinking_mode,
                    "reasons": thinking_mode_reasons,
                    "created_at": local_now_iso(),
                },
            )

        def refresh_member_context():
            self.guard.ensure_active(account_id, turn, cancellation_token)
            if member_access is not None:
                with member_access.guard() as live:
                    member_metadata.clear()
                    member_metadata.update(self.members.detail(live, self.paths))

        authorized_resource_ids: dict[str, list[str]] = {}
        for resource in user_message.get("context_resources", []):
            resource_type = str(resource.get("resource_type") or "").strip()
            resource_id = str(resource.get("resource_id") or "").strip()
            if resource_type and resource_id:
                authorized_resource_ids.setdefault(resource_type, []).append(
                    resource_id
                )
        agent_context = AgentContext(
            cancellation_token=cancellation_token,
            account_id=account_id,
            turn_id=turn_id,
            member_id=member_access.member_id if member_access is not None else None,
            task_type="conversation",
            input_text=str(user_message.get("content") or ""),
            session_id=str(turn["session_id"]),
            model_id=user_message.get("model_id"),
            resources=list(user_message.get("context_resources", [])),
            memory={
                "current_message_id": str(user_message.get("message_id") or ""),
                "visible_message_ids": sorted(visible_message_ids),
                "visible_attachments": visible_attachments,
                "attachment_parts": session_attachment_parts,
                "authorized_resource_ids": authorized_resource_ids,
                "tool_call_ids": [
                    event.data.get("call_id")
                    for event in read_events().events
                    if event.type == "tool/call"
                    and event.data.get("turn_id") == turn_id
                ],
                **({"member": member_metadata} if member_metadata else {}),
            },
        )
        model_input = ConversationModelInput(
            model=decision_model,
            user_message=user_message,
            turn_id=turn_id,
            read_events=read_events,
            check=lambda: self.guard.ensure_active(
                account_id, turn, cancellation_token
            ),
            prepare_resources=model_resources.prepare,
            input_parts=current_runtime_input_parts,
            attachment_parts=attachment_parts_by_resource_id,
            user_records=active_user_message_records,
        )
        return PreparedConversationTurn(
            agent_context,
            tool_registry,
            model_input,
            read_events,
            refresh_member_context,
            initial_skill_names,
            effective_thinking_mode,
        )
