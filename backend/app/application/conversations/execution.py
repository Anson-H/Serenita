"""连接通用 Harness、模型请求、工具观测和会话事件，执行当前轮次。"""

from copy import deepcopy
from backend.app.application.conversations.compaction import (
    DEFAULT_RESERVED_OUTPUT_TOKENS,
)
import hashlib
import json
from typing import Any, Callable


from backend.app.agent_runtime.prompts import (
    ATTACHED_ANNOTATION_PREFIX,
)
from backend.app.agent_runtime.model_types import (
    ModelRequest,
)
from backend.app.agent_runtime.compaction import (
    CompactionError,
)
from backend.app.application.model_provider_service import (
    ModelProviderService,
)
from backend.app.domain.conversations.model_history import derive_model_messages, visible_loaded_skill_names
from backend.app.core.cancellation import (
    CancellationToken,
)
from backend.app.core.time import local_now_iso
from backend.app.domain.model_capabilities import DEFAULT_CONTEXT_WINDOW_TOKENS


now_iso = local_now_iso


class ConversationExecution:
    def __init__(
        self,
        *,
        repository,
        members,
        paths,
        services,
        events,
        inputs,
        model_catalog,
        model_calls,
        compaction,
        guard,
        tool_results,
    ):
        self.repository = repository
        self.members = members
        self.paths = paths
        self.services = services
        self.events = events
        self.inputs = inputs
        self.model_catalog = model_catalog
        self.model_calls = model_calls
        self.compaction = compaction
        self.guard = guard
        self.tool_results = tool_results

    def run(
        self,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        *,
        on_workflow_event: Callable[[dict[str, Any]], None],
        on_response_delta: Callable[[str], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:
        """Run one Harness Turn, restoring Skills visible in this session."""

        self.guard.ensure_active(account_id, turn, cancellation_token)

        from backend.app.agent_runtime.context import AgentContext
        from backend.app.agent_runtime.runtime import AgentHarnessRuntime, RequestRebuilder
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
            session_events,
            current_turn_ids=[turn_id],
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
                account_id,
                session_id,
                session_file_resources,
                base_decision_model,
            )
        )
        attachment_parts_by_resource_id: dict[str, list[dict[str, Any]]] = {}
        for part in session_attachment_parts:
            resource_id = str(part.get("source_resource_id") or "")
            if resource_id:
                attachment_parts_by_resource_id.setdefault(resource_id, []).append(part)
        current_parent_tool_call_id: dict[str, str | None] = {"value": None}

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
            service_factory=lambda plugin_id: self.services.plugin_service(
                account_id,
                member_access.member_id if member_access else None,
                plugin_id,
            ),
            account_id=account_id,
            member_id=member_access.member_id if member_access is not None else None,
            event_recorder=on_workflow_event,
            observation_resolver=resolve_tool_observation,
            conversation_resource_resolver=resolve_conversation_resource,
            conversation_attachment_reader=lambda resource_id: self.inputs.read_attachment_content(
                account_id, session_id, resource_id
            ),
            message_resolver=resolve_message,
            cancellation_token=cancellation_token,
        )
        for tool in build_available_tools(runtime_context=plugin_runtime_context):
            tool_registry.register(tool)

        visible_attachments = self.inputs.visible_attachments_for_messages(
            account_id,
            session_id,
            current_message_records,
            visible_message_ids,
        )

        runtime_model_resource_observations: list[dict[str, Any]] = []

        from backend.app.application.conversations.model_resources import ConversationModelResources
        model_resources = ConversationModelResources(
            account_id=account_id, inputs=self.inputs, model_catalog=self.model_catalog,
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
            [],
            decision_model,
            resolved_resources=input_model_resources,
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
            decision_model,
            str(user_message.get("thinking_mode") or "default"),
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
                    "created_at": now_iso(),
                },
            )

        def append_model_surface(
            *,
            role: str,
            content: Any,
            message_id: str,
            tool_calls: list[dict[str, Any]] | None = None,
            pagination: dict[str, Any] | None = None,
        ) -> None:
            self.guard.ensure_active(account_id, turn, cancellation_token)
            event_type = "assistant/message" if role == "assistant" else "user/message"
            data = {
                "turn_id": turn["turn_id"],
                "message_id": message_id,
                "parent_message_id": user_message["message_id"],
                "model_id": decision_model["model_id"],
                "branch_addressable": False,
                "status": "completed",
                "content": content,
                "created_at": now_iso(),
            }
            if tool_calls is not None:
                data["tool_calls"] = tool_calls
            if pagination is not None:
                data.update(origin="harness_pagination", pagination=pagination)
            self.repository.append_session_event(
                account_id,
                turn["session_id"],
                event_type,
                data,
                surface_op="append",
            )

        def prepare_tool_result(observation):
            """Stage model input before budget/audit; roll it back on failure."""
            nonlocal decision_model
            refs = (observation.get("effects") or {}).get("model_resource_refs")
            if not isinstance(refs, list) or not refs:
                return None
            self.guard.ensure_active(account_id, turn, cancellation_token)
            previous_model = decision_model
            selected, parts = model_resource_parts(refs, decision_model)
            staged = {"call_id": observation["call_id"], "refs": refs, "parts": parts}
            decision_model = selected
            runtime_model_resource_observations.append(staged)

            def rollback():
                nonlocal decision_model
                decision_model = previous_model
                runtime_model_resource_observations.remove(staged)

            return rollback

        def handle_runtime_event(event) -> None:
            payload = dict(getattr(event, "payload", {}) or {})
            if event.type in {"tool_result", "tool_error"}:
                persisted = self.tool_results.persist(
                    account_id,
                    turn,
                    payload,
                    failed=event.type == "tool_error",
                    cancellation_token=cancellation_token,
                )
                # Cancellation stops subsequent actions, not the audit of an
                # already executed call.
                self.guard.ensure_active(account_id, turn, cancellation_token)
                if not persisted:
                    return
            else:
                self.guard.ensure_active(account_id, turn, cancellation_token)
            if event.type == "assistant_tool_calls":
                calls = list(payload.get("tool_calls") or [])
                append_model_surface(
                    role="assistant",
                    content=payload.get("content"),
                    message_id=(
                        "assistant_tools_"
                        + str(calls[0].get("id") if calls else self.repository.new_id())
                    ),
                    tool_calls=calls,
                    pagination=payload.get("pagination"),
                )
                return
            if event.type == "assistant_intermediate":
                append_model_surface(
                    role="assistant",
                    content=payload.get("content", ""),
                    message_id=f"assistant_internal_{self.repository.new_id()}",
                )
                return
            if event.type == "harness_observation":
                step = self.events.current_model_step(account_id, turn)
                self.repository.append_session_event(
                    account_id,
                    turn["session_id"],
                    "harness/observation",
                    {
                        "turn_id": turn["turn_id"],
                        "step": step,
                        "call_id": current_parent_tool_call_id["value"],
                        "observation": payload,
                        "status": "failed" if payload.get("error") else "completed",
                        "created_at": now_iso(),
                    },
                )
                return
            if event.type == "tool_call":
                tool_name = str(payload.get("tool") or "")
                call_id = str(payload.get("call_id") or "")
                current_parent_tool_call_id["value"] = str(
                    payload.get("tool_call_id") or payload.get("call_id") or ""
                )
                self.repository.append_session_event(
                    account_id,
                    turn["session_id"],
                    "tool/call",
                    {
                        "turn_id": turn["turn_id"],
                        "step": self.events.current_model_step(account_id, turn),
                        "call_id": str(payload.get("call_id")),
                        "tool_call_id": str(payload.get("tool_call_id")),
                        "name": tool_name,
                        "arguments": payload.get("arguments", {}),
                        **({"origin": "harness_pagination", "pagination": payload["pagination"]}
                           if payload.get("pagination") else {}),
                        "created_at": now_iso(),
                    },
                )
                on_workflow_event(
                    {
                        "stage": "tool",
                        "status": "started",
                        "label": tool_name,
                        "detail": "正在执行工具调用",
                        "_persisted_call_id": payload.get("call_id"),
                        "_tool_call_id": payload.get("tool_call_id"),
                        "_step": self.events.current_model_step(account_id, turn),
                        "_tool_name": tool_name,
                        "_raw_input": payload.get("arguments"),
                    }
                )
                return
            if event.type in {"tool_result", "tool_error"}:
                tool_name = str(payload.get("tool") or "")
                failed = event.type == "tool_error"
                call_id = str(payload.get("call_id") or "")
                on_workflow_event(
                    {
                        "stage": "tool",
                        "status": "failed" if failed else "completed",
                        "label": tool_name,
                        "detail": "工具调用失败，结果已返回 Agent"
                        if failed
                        else "工具调用已完成",
                        "_persisted_call_id": payload.get("call_id"),
                        "_tool_call_id": payload.get("tool_call_id"),
                        "_step": self.events.current_model_step(account_id, turn),
                        "_tool_name": tool_name,
                        "_raw_output": None if failed else payload.get("output"),
                        **({"_raw_error": payload.get("error")} if failed else {}),
                    }
                )
                current_parent_tool_call_id["value"] = None

        def derive_runtime_messages(surface_events=None) -> list[dict[str, Any]]:
            self.guard.ensure_active(account_id, turn, cancellation_token)
            messages = derive_model_messages(
                surface_events
                if surface_events is not None
                else list(read_events().events),
                current_turn_ids=[turn_id],
                include_user_context=True,
            )
            current_message_id = str(user_message.get("message_id") or "")
            included_user_message_ids: set[str] = set()
            for message in messages:
                message_id = str(message.pop("_message_id", "") or "")
                resources = message.pop("_context_resources", [])
                if message.get("role") != "user" or not message_id:
                    continue
                included_user_message_ids.add(message_id)
                input_parts: list[dict[str, Any]] = []
                for resource in resources:
                    if not isinstance(resource, dict):
                        continue
                    resource_id = str(resource.get("resource_id") or "")
                    input_parts.extend(
                        dict(part)
                        for part in attachment_parts_by_resource_id.get(resource_id, [])
                    )
                if message_id == current_message_id:
                    input_parts.extend(
                        dict(part) for part in current_runtime_input_parts
                    )
                if not input_parts:
                    continue
                content = message.get("content")
                if isinstance(content, list):
                    message["content"] = [*content, *input_parts]
                else:
                    message["content"] = [
                        {"type": "text", "text": str(content or "")},
                        *input_parts,
                    ]
            compacted_attachment_messages: list[dict[str, Any]] = []
            for message_record in active_user_message_records:
                message_id = str(
                    message_record.get("message_id")
                    or message_record.get("record_id")
                    or ""
                )
                if not message_id or message_id in included_user_message_ids:
                    continue
                input_parts: list[dict[str, Any]] = []
                for resource in message_record.get("context_resources", []):
                    if not isinstance(resource, dict):
                        continue
                    resource_id = str(resource.get("resource_id") or "")
                    input_parts.extend(
                        dict(part)
                        for part in attachment_parts_by_resource_id.get(resource_id, [])
                    )
                if input_parts:
                    compacted_attachment_messages.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": "历史附件原文（相关用户请求见历史摘要）。",
                                },
                                *input_parts,
                            ],
                        }
                    )
            if compacted_attachment_messages:
                messages = [*compacted_attachment_messages, *messages]
            resource_messages: list[dict[str, Any]] = []
            for observation in runtime_model_resource_observations:
                resource_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": "TOOL_RESOURCE_OBSERVATION\n"
                                + json.dumps(
                                    {
                                        "tool_call_id": observation["call_id"],
                                        "resources": observation["refs"],
                                    },
                                    ensure_ascii=False,
                                    separators=(",", ":"),
                                ),
                            },
                            *observation["parts"],
                        ],
                    }
                )
            # Resource observations are user messages. Keep them outside a
            # pending native tool group while checking a candidate result.
            pending_ids: set[str] = set()
            pending_start = len(messages)
            for index, message in enumerate(messages):
                if message.get("role") == "assistant" and message.get("tool_calls"):
                    pending_start = index
                    pending_ids = {str(call["id"]) for call in message["tool_calls"]}
                elif message.get("role") == "tool":
                    pending_ids.discard(str(message.get("tool_call_id") or ""))
            insertion = pending_start if pending_ids else len(messages)
            messages[insertion:insertion] = resource_messages
            seen_parts: set[str] = set()
            for message in messages:
                if not isinstance(message.get("content"), list):
                    continue
                unique_parts = []
                for part in message["content"]:
                    if not isinstance(part, dict) or (
                        part.get("type") == "text"
                        and not part.get("source_resource_id")
                        and not part.get("model_resource_ref")
                    ):
                        unique_parts.append(part)
                        continue
                    key = hashlib.sha256(
                        json.dumps(part, sort_keys=True).encode()
                    ).hexdigest()
                    if key not in seen_parts:
                        unique_parts.append(part)
                        seen_parts.add(key)
                message["content"] = unique_parts
            return [message for message in messages if message.get("content") != []]

        def refresh_member_context():
            self.guard.ensure_active(account_id, turn, cancellation_token)
            if member_access is not None:
                with member_access.guard() as live:
                    member_metadata.clear()
                    member_metadata.update(self.members.detail(live, self.paths))

        def complete_agent_step(request: ModelRequest):
            self.guard.ensure_active(account_id, turn, cancellation_token)
            return self.model_calls.complete_chat_with_events(
                account_id=account_id,
                turn=turn,
                user_message=user_message,
                model=decision_model,
                model_request=request,
                thinking_mode=self.inputs.thinking_mode_for_model(
                    decision_model,
                    effective_thinking_mode,
                ),
                purpose="agent_action",
                timeout_seconds=90,
                cancellation_token=cancellation_token,
            )

        runtime = AgentHarnessRuntime(tool_registry=tool_registry)
        authorized_resource_ids: dict[str, list[str]] = {}
        for resource in user_message.get("context_resources", []):
            resource_type = str(resource.get("resource_type") or "").strip()
            resource_id = str(resource.get("resource_id") or "").strip()
            if resource_type and resource_id:
                authorized_resource_ids.setdefault(resource_type, []).append(
                    resource_id
                )
        agent_context = AgentContext(
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
                "tool_call_ids": [event.data.get("call_id") for event in read_events().events if event.type == "tool/call" and event.data.get("turn_id") == turn_id],
                **({"member": member_metadata} if member_metadata else {}),
            },
        )
        failed_compactions: set[str] = set()

        def derive_skill_names():
            return visible_loaded_skill_names(
                list(read_events().events),
                current_turn_ids=[turn_id],
            )

        def prepare_action_request(
            request: ModelRequest,
            rebuild_request: RequestRebuilder,
            force: bool = False,
            *,
            tool_result: bool = False,
        ):
            refresh_member_context()

            def rebuild(surface_events):
                refresh_member_context()
                return rebuild_request(
                    messages=derive_runtime_messages(surface_events),
                    skill_names=visible_loaded_skill_names(
                        surface_events,
                        current_turn_ids=[turn_id],
                    ),
                )

            try:
                return self.compaction.compact_model_request_if_needed(
                    account_id=account_id,
                    turn=turn,
                    user_message=user_message,
                    model=decision_model,
                    model_request=request,
                    thinking_mode=effective_thinking_mode,
                    rebuild_request=rebuild,
                    cancellation_token=cancellation_token,
                    force=force,
                    reason="tool_result" if tool_result else "threshold",
                    failed_fingerprints=failed_compactions,
                    allow_pending=tool_result,
                )
            except CompactionError:
                if tool_result:
                    # The runtime returns a bounded, truthful size error for
                    # this already-executed call, then resumes its action loop.
                    return request
                raise

        result = runtime.execute(
            agent_context,
            initial_skill_names=initial_skill_names,
            on_event=handle_runtime_event,
            derive_messages=derive_runtime_messages,
            complete_model=complete_agent_step,
            before_model_request=refresh_member_context,
            derive_skill_names=derive_skill_names,
            prepare_request=prepare_action_request,
            before_tool_result=lambda request, rebuild: prepare_action_request(
                request, rebuild, tool_result=True
            ),
            prepare_tool_result=prepare_tool_result,
            tool_result_context_budget=lambda: (
                int(decision_model.get("context_window_tokens") or DEFAULT_CONTEXT_WINDOW_TOKENS),
                int(decision_model.get("max_output_tokens") or DEFAULT_RESERVED_OUTPUT_TOKENS),
            ),
            estimate_request_tokens=lambda request: (
                self.compaction.estimate_model_request_tokens(
                    ModelProviderService.prepare_transport_request(
                        decision_model, request, effective_thinking_mode
                    )
                )
            ),
            context_window_tokens=(
                int(
                    decision_model.get("context_window_tokens")
                    or DEFAULT_CONTEXT_WINDOW_TOKENS
                )
            ),
            reserved_output_tokens=int(
                decision_model.get("max_output_tokens")
                or DEFAULT_RESERVED_OUTPUT_TOKENS
            ),
        )
        self.guard.ensure_active(account_id, turn, cancellation_token)
        return {**result.output, "model_id": decision_model["model_id"]}
