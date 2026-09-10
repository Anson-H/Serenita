from __future__ import annotations

from backend.app.agent_runtime.tools.parameters import validate_parameters

from dataclasses import dataclass, replace
from copy import deepcopy
from collections import deque
from uuid import uuid4
import json
import math
from typing import Any, Callable, Iterable, Protocol

from backend.app.agent_runtime.context import AgentContext
from backend.app.agent_runtime.compaction import TRIGGER_RATIO
from backend.app.agent_runtime.events import AgentEvent
from backend.app.agent_runtime.model_types import (
    AssistantModelOutput,
    ModelRequest,
    ToolCall,
    ToolSchema,
)
from backend.app.agent_runtime.prompts import assemble_serenita_prompt
from backend.app.agent_runtime.skills import build_builtin_skills
from backend.app.agent_runtime.skills.registry import (
    SkillNotFoundError,
    SkillRegistry,
)
from backend.app.agent_runtime.tools.registry import ToolRegistry
from backend.app.agent_runtime.tools.base import ToolResult
from backend.app.agent_runtime.tools.errors import stops_execution, tool_failure
from backend.app.core.tabular_json import encode_tabular_json
from backend.app.core.time import local_now
from backend.app.domain.model_capabilities import DEFAULT_CONTEXT_WINDOW_TOKENS
from backend.app.providers.errors import ProviderChatCompletionError


CONTROL_TOOL_NAMES = frozenset({"load_skill", "update_plan"})
SERVER_BOUND_ARGUMENT_NAMES = frozenset(
    {
        "account_id",
        "model_id",
        "parsed_observation_tokens",
        "session_id",
        "source_message_id",
        "visible_message_ids",
        "visible_attachments",
        "source_text",
    }
)


@dataclass(frozen=True)
class RuntimeResult:
    output: dict[str, Any]
    events: list[AgentEvent]


@dataclass(frozen=True)
class PendingReadPage:
    call: ToolCall
    load: Callable[[], ToolResult]
    root_call_id: str
    number: int


class RequestRebuilder(Protocol):
    """Rebuild from durable messages and their visible skill names.

    The Harness adds any pending tool result and skill activation, and keeps
    suspended tools unavailable. Callers supply history without that pending
    result; repeated calls do not change execution state.
    """

    def __call__(
        self, *, messages: list[dict[str, Any]], skill_names: Iterable[str]
    ) -> ModelRequest: ...


class AgentHarnessRuntime:
    """Generic, event-driven Skill and Tool loop for a Serenita turn."""

    def __init__(
        self,
        *,
        skill_registry: SkillRegistry | None = None,
        tool_registry: ToolRegistry | None = None,
        max_actions: int = 24,
        max_repeated_calls: int = 2,
    ):
        self.skill_registry = skill_registry or SkillRegistry()
        if skill_registry is None:
            for skill in build_builtin_skills():
                self.skill_registry.register(skill)
        self.tool_registry = tool_registry or ToolRegistry()
        self.max_actions = max(1, int(max_actions))
        self.max_repeated_calls = max(1, int(max_repeated_calls))

    def execute(
        self,
        context: AgentContext,
        *,
        initial_skill_names: Iterable[str] = (),
        derive_messages: Callable[[], list[dict[str, Any]]],
        complete_model: Callable[[ModelRequest], AssistantModelOutput],
        before_model_request: Callable[[], None] | None = None,
        prepare_request: Callable[[ModelRequest, RequestRebuilder, bool], ModelRequest] | None = None,
        derive_skill_names: Callable[[], Iterable[str]] | None = None,
        before_tool_result: Callable[[ModelRequest, RequestRebuilder], ModelRequest] | None = None,
        on_event: Callable[[AgentEvent], None] | None = None,
        estimate_request_tokens: Callable[[ModelRequest], int] | None = None,
        context_window_tokens: int | None = None,
        reserved_output_tokens: int = 4096,
        prepare_tool_result: Callable[[dict[str, Any]], Callable[[], None] | None] | None = None,
        tool_result_context_budget: Callable[[], tuple[int, int]] | None = None,
    ) -> RuntimeResult:
        events: list[AgentEvent] = []

        def emit(event: AgentEvent) -> None:
            events.append(event)
            if on_event is not None:
                on_event(event)

        read_skills: dict[str, Any] = {}

        def sync_read_skills(skill_names: Iterable[str]) -> None:
            read_skills.clear()
            for skill_name in skill_names:
                normalized = str(skill_name or "").strip()
                if not normalized or normalized in read_skills:
                    continue
                try:
                    skill = self.skill_registry.get(normalized)
                except SkillNotFoundError:
                    continue
                read_skills[normalized] = skill.read(context)

        if derive_skill_names is None:
            sync_read_skills(initial_skill_names or ())
        tool_results: list[dict[str, Any]] = []
        repeated_calls: dict[str, int] = {}
        suspended_tools: set[str] = set()
        call_ids = set(context.memory.get("tool_call_ids") or ())
        latest_observation: dict[str, Any] = {
            "type": "turn_started",
            "resource_count": len(context.resources),
        }
        pending_pages: deque[PendingReadPage] = deque()
        action_count = 0
        while action_count < self.max_actions or pending_pages:
            if before_model_request is not None:
                before_model_request()
            if derive_skill_names is not None:
                sync_read_skills(derive_skill_names())
            assembly = self.assemble_request_context(
                read_skills=read_skills,
                context=context,
                suspended_tools=suspended_tools,
            )
            request = ModelRequest.build(
                system=assembly.system,
                messages=derive_messages(),
                tools=assembly.tools,
                context_sections=assembly.context_sections,
                tool_choice="auto",
                model_config={"purpose": "agent_action"},
            )
            if prepare_request is not None:
                request = prepare_request(
                    request,
                    self._request_rebuilder(
                        context=context, read_skills=read_skills,
                        suspended_tools=suspended_tools, template=request,
                    ),
                    False,
                )
            if pending_pages:
                pending = pending_pages.popleft()
                call_ids.add(pending.call.id)
                emit(AgentEvent(type="assistant_tool_calls", payload={
                    "content": f"继续读取同一查询的第 {pending.number} 页。",
                    "tool_calls": [pending.call.as_dict()],
                    "pagination": {"root_call_id": pending.root_call_id, "page": pending.number},
                }))
                self._execute_call(
                    call=pending.call, available={item.name: item for item in request.tools},
                    context=context, read_skills=read_skills, tool_results=tool_results,
                    repeated_calls=repeated_calls, suspended_tools=suspended_tools,
                    emit=emit, request=request, derive_messages=derive_messages,
                    before_tool_result=before_tool_result,
                    estimate_request_tokens=estimate_request_tokens,
                    context_window_tokens=context_window_tokens,
                    reserved_output_tokens=reserved_output_tokens,
                    prepare_tool_result=prepare_tool_result,
                    tool_result_context_budget=tool_result_context_budget,
                    pending_pages=pending_pages, continuation=pending,
                )
                continue
            action_count += 1
            try:
                try:
                    model_output = complete_model(request)
                except ProviderChatCompletionError as exc:
                    if (
                        getattr(exc, "code", None) != "CONTEXT_WINDOW_EXCEEDED"
                        or prepare_request is None
                    ):
                        raise
                    # The Service must reject compaction without progress. Retry
                    # only this model call, before emitting or executing actions.
                    request = prepare_request(
                        request,
                        self._request_rebuilder(
                            context=context, read_skills=read_skills,
                            suspended_tools=suspended_tools, template=request,
                        ),
                        True,
                    )
                    model_output = complete_model(request)
            except ProviderChatCompletionError as exc:
                if "文本工具协议" in str(exc):
                    latest_observation = {
                        "type": "protocol_error",
                        "error": {
                            "code": "TEXT_TOOL_PROTOCOL_INVALID",
                            "message": str(exc),
                        },
                    }
                    emit(
                        AgentEvent(
                            type="harness_observation",
                            payload=latest_observation,
                        )
                    )
                raise

            if model_output.tool_calls:
                tool_calls = model_output.tool_calls
                ids = [call.id for call in tool_calls]
                if len(ids) != len(set(ids)) or call_ids.intersection(ids):
                    emit(AgentEvent(type="harness_observation", payload={
                        "type": "protocol_error",
                        "error": {
                            "code": "TOOL_CALL_ID_CONFLICT",
                            "message": "工具调用标识重复；该批调用均未执行，请使用新的调用标识。",
                            "details": {"rejected_tool_calls": [call.as_dict() for call in tool_calls]},
                        },
                    }))
                    continue
                call_ids.update(ids)
                emit(
                    AgentEvent(
                        type="assistant_tool_calls",
                        payload={
                            "content": model_output.content or None,
                            "reasoning": model_output.reasoning,
                            "tool_calls": [item.as_dict() for item in tool_calls],
                        },
                    )
                )
                available = {item.name: item for item in request.tools}
                for call in tool_calls:
                    self._execute_call(
                        call=call,
                        available=available,
                        context=context,
                        read_skills=read_skills,
                        tool_results=tool_results,
                        repeated_calls=repeated_calls,
                        suspended_tools=suspended_tools,
                        emit=emit,
                        request=request,
                        derive_messages=derive_messages,
                        before_tool_result=before_tool_result,
                        estimate_request_tokens=estimate_request_tokens,
                        context_window_tokens=context_window_tokens,
                        reserved_output_tokens=reserved_output_tokens,
                        prepare_tool_result=prepare_tool_result,
                        tool_result_context_budget=tool_result_context_budget,
                        pending_pages=pending_pages,
                    )
                continue

            content = str(model_output.content or "").strip()
            if not model_output.has_final_stop:
                if content:
                    emit(AgentEvent(type="assistant_intermediate", payload={"content": content}))
                emit(AgentEvent(type="harness_observation", payload={
                    "type": "action_error",
                    "error": {
                        "code": "MODEL_OUTPUT_INCOMPLETE",
                        "message": "模型输出未正常完成，请根据已保留的内容决定继续、调整行动或说明无法完成。",
                        "stop_reason": model_output.stop_reason,
                    },
                }))
                continue
            if not content:
                latest_observation = {
                    "type": "action_error",
                    "error": {
                        "code": "EMPTY_MODEL_ACTION",
                        "message": "模型既未调用工具，也未返回回答。",
                    },
                }
                emit(
                    AgentEvent(
                        type="harness_observation",
                        payload=latest_observation,
                    )
                )
                continue

            terminal = {"content": content}
            emit(AgentEvent(type="final_response", payload=terminal))
            return RuntimeResult(
                output={
                    "status": "completed",
                    "tool_results": tool_results,
                    "terminal_action": terminal,
                },
                events=events,
            )

        raise RuntimeError("Agent Runtime 超过当前轮次最大行动次数。")

    def _execute_call(
        self,
        *,
        call: ToolCall,
        available: dict[str, ToolSchema],
        context: AgentContext,
        read_skills: dict[str, Any],
        tool_results: list[dict[str, Any]],
        repeated_calls: dict[str, int],
        suspended_tools: set[str],
        emit: Callable[[AgentEvent], None],
        request: ModelRequest,
        derive_messages: Callable[[], list[dict[str, Any]]],
        before_tool_result: Callable[[ModelRequest, RequestRebuilder], ModelRequest] | None,
        estimate_request_tokens: Callable[[ModelRequest], int] | None,
        context_window_tokens: int | None,
        reserved_output_tokens: int,
        prepare_tool_result: Callable[[dict[str, Any]], Callable[[], None] | None] | None = None,
        tool_result_context_budget: Callable[[], tuple[int, int]] | None = None,
        pending_pages: deque[PendingReadPage] | None = None,
        continuation: PendingReadPage | None = None,
    ) -> dict[str, Any]:
        pending_skills: dict[str, Any] = {}

        def prepare_candidate(candidate: ModelRequest) -> ModelRequest:
            assert before_tool_result is not None
            return before_tool_result(
                candidate,
                self._request_rebuilder(
                    context=context, read_skills=read_skills,
                    suspended_tools=suspended_tools, template=candidate,
                    pending_messages=(candidate.messages[-1],),
                    pending_skills=pending_skills,
                ),
            )

        finish_arguments = dict(
            call=call, tool_results=tool_results, emit=emit, request=request,
            derive_messages=derive_messages,
            before_tool_result=prepare_candidate if before_tool_result is not None else None,
            estimate_request_tokens=estimate_request_tokens,
            context_window_tokens=context_window_tokens,
            reserved_output_tokens=reserved_output_tokens,
            prepare_tool_result=prepare_tool_result,
            tool_result_context_budget=tool_result_context_budget,
        )
        visible_arguments = dict(call.arguments)
        emit(
            AgentEvent(
                type="tool_call",
                payload={
                    "call_id": call.id,
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "arguments": visible_arguments,
                    "control": call.name in CONTROL_TOOL_NAMES,
                    **({"pagination": {"root_call_id": continuation.root_call_id,
                                        "page": continuation.number}} if continuation else {}),
                },
            )
        )
        # A continuation completes a previously admitted read. Its exact query
        # survives compaction even when the granting skill leaves model context;
        # this does not restore that tool to the model's available capabilities.
        if continuation is None and call.name not in available:
            return self._emit_tool_error(
                call,
                code="TOOL_NOT_ALLOWED",
                message="该工具不在当前请求允许的工具集合中。",
                emit=emit,
            )

        if call.name == "load_skill":
            try:
                self._validate_schema(
                    call.arguments,
                    available[call.name].parameters,
                    label="工具 load_skill 参数",
                )
            except Exception as exc:
                return self._emit_tool_error(
                    call,
                    code="TOOL_ARGUMENTS_INVALID",
                    message=str(exc) or "技能读取参数无效。",
                    emit=emit,
                )
            skill_name = str(call.arguments.get("name") or "").strip()
            try:
                skill_content = self.skill_registry.get(skill_name).read(context)
                registered_tools = {
                    item["name"] for item in self.tool_registry.catalog(context=context)
                }
                missing_tools = sorted(
                    set(skill_content.allowed_tools) - registered_tools
                )
                if missing_tools:
                    raise ValueError(
                        "技能引用了未注册工具：" + "、".join(missing_tools)
                    )
            except Exception as exc:
                return self._emit_tool_error(
                    call,
                    code="SKILL_READ_FAILED",
                    message=str(exc) or "技能读取失败。",
                    emit=emit,
                )
            # The next request contains both this body and the schemas it
            # authorizes. Budget them together before activating the skill.
            pending_skills[skill_name] = skill_content
            finish_arguments["request"] = self._rebuild_request(
                context=context,
                read_skills={**read_skills, skill_name: skill_content},
                suspended_tools=suspended_tools,
                template=request,
                messages=list(request.messages),
            )
            observation = self._finish_tool_result(
                result=ToolResult(call.name, {"content": skill_content.content}),
                wire_output=skill_content.content,
                retain_in_observations=False,
                **finish_arguments,
            )
            if observation.get("type") == "tool_result":
                read_skills[skill_name] = skill_content
            return observation

        if call.name == "update_plan":
            try:
                self._validate_schema(
                    call.arguments,
                    available[call.name].parameters,
                    label="工具 update_plan 参数",
                )
            except Exception as exc:
                return self._emit_tool_error(
                    call,
                    code="TOOL_ARGUMENTS_INVALID",
                    message=str(exc) or "任务计划参数无效。",
                    emit=emit,
                )
            return self._finish_tool_result(
                result=ToolResult(call.name, dict(call.arguments)), **finish_arguments
            )

        arguments = dict(call.arguments)
        reserved_arguments = sorted(set(arguments) & SERVER_BOUND_ARGUMENT_NAMES)
        if reserved_arguments:
            return self._emit_tool_error(
                call,
                code="SERVER_BOUND_ARGUMENT_REJECTED",
                message=(
                    "以下参数只能由服务端绑定，模型不得提供："
                    + "、".join(reserved_arguments)
                ),
                emit=emit,
            )
        try:
            tool = self.tool_registry.get(call.name)
            input_schema = dict(tool.input_schema_for_context(context) or {})
            invalid_key = tool.invalid_repetition_key(arguments, context=context)
            if invalid_key:
                repeated_calls[invalid_key] = repeated_calls.get(invalid_key, 0) + 1
                if repeated_calls[invalid_key] > 1:
                    suspended_tools.add(call.name)
                    return self._emit_tool_error(
                        call,
                        code="REPEATED_INVALID_TOOL_ARGUMENTS",
                        message=(
                            "同一工具再次提交了语义等价的无效参数；"
                            "该工具已在当前轮次暂停，请依据已给出的允许值说明失败或结束当前轮次。"
                        ),
                        emit=emit,
                    )
            self._validate_schema(
                arguments,
                input_schema,
                label=f"工具 {call.name} 参数",
            )
        except Exception as exc:
            if "tool" in locals():
                code, message = tool.validation_error(arguments, exc, context=context)
                if code == "TOOL_ARGUMENTS_INVALID":
                    invalid_schema_key = f"{call.name}:schema_validation"
                    repeated_calls[invalid_schema_key] = (
                        repeated_calls.get(invalid_schema_key, 0) + 1
                    )
                    if repeated_calls[invalid_schema_key] > self.max_repeated_calls:
                        suspended_tools.add(call.name)
                        code = "REPEATED_INVALID_TOOL_ARGUMENTS"
                        message = (
                            f"{message} 同一工具已连续提交无效结构，"
                            "当前轮次不再继续调用该工具；请依据已有工具观测说明失败或结束当前轮次。"
                        )
            else:
                code, message = (
                    "TOOL_ARGUMENTS_INVALID",
                    str(exc) or "工具参数无效。",
                )
            return self._emit_tool_error(
                call,
                code=code,
                message=message,
                emit=emit,
            )
        call_key = self._call_key(call.name, arguments)
        if continuation is None:
            repeated_calls[call_key] = repeated_calls.get(call_key, 0) + 1
        if continuation is None and repeated_calls[call_key] > self.max_repeated_calls:
            return self._emit_tool_error(
                call,
                code="REPEATED_TOOL_CALL_LIMIT",
                message=f"检测到超过预算的重复工具调用：{call.name}",
                emit=emit,
            )
        try:
            bound = tool.bind_runtime_arguments(
                arguments,
                context=context,
                observations=tool_results,
            )
            result = continuation.load() if continuation else tool.run(bound)
            if continuation is not None and result.name != call.name:
                raise ValueError("自动续读不能切换工具。")
        except Exception as exc:
            failure = tool_failure(exc)
            if continuation is not None:
                failure["details"] = {
                    **(failure.get("details") or {}),
                    "pagination": {"root_call_id": continuation.root_call_id,
                                   "page": continuation.number, "complete": False},
                }
            return self._emit_tool_error(
                call,
                **failure,
                emit=emit,
            )
        observation = self._finish_tool_result(result=result, **finish_arguments)
        if observation.get("type") == "tool_result" and result.next_page is not None:
            if pending_pages is None:
                raise RuntimeError("自动读取缺少 Harness 分页队列。")
            pending_pages.append(PendingReadPage(
                call=ToolCall(id="page_" + uuid4().hex, name=call.name, arguments=deepcopy(call.arguments)),
                load=result.next_page,
                root_call_id=continuation.root_call_id if continuation else call.id,
                number=continuation.number + 1 if continuation else 2,
            ))
        return observation

    def _finish_tool_result(
        self, *, result, call, tool_results, emit, request, derive_messages,
        before_tool_result, estimate_request_tokens, context_window_tokens,
        reserved_output_tokens, prepare_tool_result=None, wire_output=None,
        tool_result_context_budget=None,
        retain_in_observations=True,
    ):
        """Prepare, budget and audit every completed tool through one exit."""
        output = self._assemble_tool_output(result)
        observation = {
            "type": "tool_result",
            "call_id": call.id,
            "name": result.name,
            "output": output,
            "effects": dict(getattr(result, "effects", {}) or {}),
            "trust": "untrusted_data_only",
        }
        encoded_observation = wire_output if wire_output is not None else {
            **observation,
            "output": encode_tabular_json(output),
        }

        def retain_result() -> None:
            if not retain_in_observations:
                return
            tool_results.append(
                {
                    "call_id": call.id,
                    "name": result.name,
                    "output": output,
                    "effects": observation["effects"],
                }
            )

        rollback_preparation = None
        preparing_result = prepare_tool_result is not None
        try:
            if prepare_tool_result is not None:
                rollback_preparation = prepare_tool_result(observation)
            preparing_result = False
            if tool_result_context_budget is not None:
                context_window_tokens, reserved_output_tokens = tool_result_context_budget()
            budget_error = self._tool_result_budget_error(
                call=call,
                result=result,
                assembled_output=output,
                encoded_observation=encoded_observation,
                request=request,
                derive_messages=derive_messages,
                before_tool_result=before_tool_result,
                estimate_request_tokens=estimate_request_tokens,
                context_window_tokens=context_window_tokens,
                reserved_output_tokens=reserved_output_tokens,
            )
        except Exception as exc:
            # Audit the executed result before either returning a capability
            # failure to the model or propagating a security/cancellation stop.
            retain_result()
            if rollback_preparation is not None:
                rollback_preparation()
            failure = tool_failure(exc)
            error_observation = self._emit_tool_error(
                call,
                code=failure["code"],
                message=failure["message"],
                details={
                    **(failure["details"] or {}),
                    "execution_completed": True,
                    "effects": observation["effects"],
                },
                output=encoded_observation,
                emit=emit,
            )
            if not preparing_result or stops_execution(exc):
                raise
            return error_observation
        if budget_error is not None:
            if rollback_preparation is not None:
                rollback_preparation()
            retain_result()
            budget_error = {
                **budget_error,
                "execution_completed": True,
                "effects": observation["effects"],
            }
            paginated = isinstance(output.get("pagination"), dict)
            if paginated:
                budget_error["pagination"] = {**output["pagination"], "complete": False}
            return self._emit_tool_error(
                call,
                code="TOOL_RESULT_TOO_LARGE",
                message=("本页已读取，但完整内容无法装入当前模型上下文；本页未返回部分内容，整个查询尚未完成。"
                         if paginated else "工具已执行，完整结果无法装入当前模型上下文；未返回任何部分结果。"),
                details=budget_error,
                output=encoded_observation,
                emit=emit,
            )
        retain_result()
        # Persist the lossless columnar form; in-turn trust derivation keeps
        # the raw output, and cross-turn consumers decode before use.
        self._emit_tool_result(call, encoded_observation, emit=emit)
        return observation

    @staticmethod
    def _merge_tool_page(
        output: dict[str, Any], page: dict[str, Any]
    ) -> dict[str, Any]:
        merged = deepcopy(output)
        for key, value in page.items():
            if isinstance(value, list):
                current = merged.get(key)
                if current is None:
                    merged[key] = deepcopy(value)
                elif isinstance(current, list):
                    current.extend(deepcopy(value))
                else:
                    raise ValueError(f"逻辑页字段 {key} 与基础结果类型不一致。")
                continue
            if key in merged and merged[key] != value:
                raise ValueError(f"逻辑页字段 {key} 在不同页面中不一致。")
            merged[key] = deepcopy(value)
        return merged

    @classmethod
    def _assemble_tool_output(cls, result: Any) -> dict[str, Any]:
        output = deepcopy(dict(result.output or {}))
        for page in tuple(getattr(result, "logical_pages", ()) or ()):
            if not isinstance(page, dict):
                raise ValueError("工具逻辑页必须是对象。")
            output = cls._merge_tool_page(output, page)
        return output

    @staticmethod
    def _default_request_token_estimate(request: ModelRequest) -> int:
        payload = {
            "system": request.system,
            "messages": list(request.messages),
            "tools": [item.as_dict() for item in request.tools],
            "tool_choice": request.tool_choice,
            "model_config": dict(request.model_config),
        }
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return max(1, math.ceil(len(serialized.encode("utf-8")) / 4))

    @staticmethod
    def _candidate_request(
        *,
        call: ToolCall,
        observation: dict[str, Any],
        request: ModelRequest,
        derive_messages: Callable[[], list[dict[str, Any]]],
    ) -> ModelRequest:
        messages = list(derive_messages())
        messages.append(
            {
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": observation if isinstance(observation, str) else json.dumps(
                    observation,
                    ensure_ascii=False,
                    separators=(",", ":"),
                    default=str,
                ),
            }
        )
        return replace(request, messages=tuple(messages))

    @classmethod
    def _tool_result_budget_error(
        cls,
        *,
        call: ToolCall,
        result: Any,
        assembled_output: dict[str, Any],
        encoded_observation: dict[str, Any],
        request: ModelRequest,
        derive_messages: Callable[[], list[dict[str, Any]]],
        before_tool_result: Callable[[ModelRequest], ModelRequest] | None,
        estimate_request_tokens: Callable[[ModelRequest], int] | None,
        context_window_tokens: int | None,
        reserved_output_tokens: int,
    ) -> dict[str, Any] | None:
        try:
            context_window = int(context_window_tokens or DEFAULT_CONTEXT_WINDOW_TOKENS)
        except (TypeError, ValueError):
            context_window = DEFAULT_CONTEXT_WINDOW_TOKENS
        if context_window <= 0:
            context_window = DEFAULT_CONTEXT_WINDOW_TOKENS
        try:
            reserved_output = max(1, int(reserved_output_tokens))
        except (TypeError, ValueError):
            reserved_output = 4096
        available_tokens = max(0, context_window - reserved_output)
        candidate = cls._candidate_request(
            call=call,
            observation=encoded_observation,
            request=request,
            derive_messages=derive_messages,
        )
        estimator = estimate_request_tokens or cls._default_request_token_estimate
        estimated_required = max(1, int(estimator(candidate)))
        if estimated_required >= int(available_tokens * TRIGGER_RATIO) and before_tool_result is not None:
            candidate = before_tool_result(candidate)
            estimated_required = max(1, int(estimator(candidate)))
        if estimated_required <= available_tokens:
            return None

        pages = tuple(getattr(result, "logical_pages", ()) or ())
        if not pages:
            pages = (assembled_output,)
            base_output: dict[str, Any] = {}
        else:
            base_output = deepcopy(dict(result.output or {}))
        fitted_pages = 0
        partial_output = base_output
        for page in pages if isinstance(encoded_observation, dict) else ():
            partial_output = cls._merge_tool_page(partial_output, page)
            partial_observation = {
                **encoded_observation,
                "output": encode_tabular_json(partial_output),
            }
            partial_candidate = replace(
                candidate,
                messages=tuple(
                    {
                        **message,
                        "content": json.dumps(
                            partial_observation,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            default=str,
                        ),
                    }
                    if message.get("role") == "tool"
                    and message.get("tool_call_id") == call.id
                    else message
                    for message in candidate.messages
                ),
            )
            partial_tokens = max(1, int(estimator(partial_candidate)))
            if partial_tokens > available_tokens:
                break
            fitted_pages += 1
        return {
            "tool_name": call.name,
            "logical_total_pages": len(pages),
            "fitted_pages": fitted_pages,
            "estimated_required_tokens": estimated_required,
            "available_tokens": available_tokens,
            "context_window_tokens": context_window,
            "reserved_output_tokens": reserved_output,
        }

    def _request_rebuilder(
        self,
        *,
        context: AgentContext,
        read_skills: dict[str, Any],
        suspended_tools: set[str],
        template: ModelRequest,
        pending_messages: tuple[dict[str, Any], ...] = (),
        pending_skills: dict[str, Any] | None = None,
    ) -> RequestRebuilder:
        """Capture the execution state that a history checkpoint cannot supply."""

        loaded = dict(read_skills)
        pending = dict(pending_skills or {})
        suspended = set(suspended_tools)
        retained_messages = deepcopy(pending_messages)
        assembly_time = local_now().isoformat()

        def rebuild(
            *, messages: list[dict[str, Any]], skill_names: Iterable[str]
        ) -> ModelRequest:
            visible_skills: dict[str, Any] = {}
            for name in skill_names:
                name = str(name or "").strip()
                if not name or name in visible_skills:
                    continue
                if name in loaded:
                    visible_skills[name] = loaded[name]
                    continue
                try:
                    visible_skills[name] = self.skill_registry.get(name).read(context)
                except SkillNotFoundError:
                    continue
            visible_skills.update(pending)
            return self._rebuild_request(
                context=context,
                read_skills=visible_skills,
                suspended_tools=suspended,
                template=template,
                messages=[*messages, *deepcopy(retained_messages)],
                runtime_context_overrides={"current_time": assembly_time},
            )

        return rebuild

    def _rebuild_request(
        self,
        *,
        context: AgentContext,
        read_skills: dict[str, Any],
        suspended_tools: set[str],
        template: ModelRequest,
        messages: list[dict[str, Any]],
        runtime_context_overrides: dict[str, Any] | None = None,
    ) -> ModelRequest:
        """Rebuild authorized model context from the current durable history."""
        assembly = self.assemble_request_context(
            read_skills=read_skills,
            context=context,
            suspended_tools=suspended_tools,
            runtime_context={
                **self._model_runtime_context(context),
                **(runtime_context_overrides or {}),
            },
        )
        return ModelRequest.build(
            system=assembly.system,
            tools=assembly.tools,
            context_sections=assembly.context_sections,
            messages=messages,
            model_config=template.model_config,
            tool_choice=template.tool_choice,
            transport_mode=template.transport_mode,
        )

    def assemble_request_context(
        self,
        *,
        read_skills: dict[str, Any],
        context: AgentContext,
        suspended_tools: set[str],
        runtime_context: dict[str, Any] | None = None,
    ):
        allowed = {
            tool_name
            for skill_content in read_skills.values()
            for tool_name in skill_content.allowed_tools
        }
        application_tools = [
            ToolSchema.from_catalog_entry(item)
            for item in self.tool_registry.catalog(context=context)
            if (
                item.get("model_exposure", "skill") == "direct"
                or item["name"] in allowed
            )
            and item["name"] not in suspended_tools
        ]
        return assemble_serenita_prompt(
            available_skills=self.skill_registry.catalog(),
            application_tools=application_tools,
            runtime_context=(
                self._model_runtime_context(context)
                if runtime_context is None
                else runtime_context
            ),
        )

    @staticmethod
    def _model_runtime_context(context: AgentContext) -> dict[str, Any]:
        visible_attachments = context.memory.get("visible_attachments") or {}
        attachments = []
        for resource_id, metadata in sorted(visible_attachments.items()):
            item = metadata if isinstance(metadata, dict) else {}
            attachments.append(
                {
                    "resource_id": str(resource_id),
                    "original_filename": str(item.get("original_filename") or ""),
                    "mime_type": str(item.get("mime_type") or ""),
                }
            )
        now = local_now()
        return {
            "current_time": now.isoformat(),
            "attachment_metadata_trust": "untrusted_data_only",
            "visible_attachments": attachments,
            **(
                {"member": context.memory["member"]}
                if context.memory.get("member")
                else {}
            ),
        }

    @staticmethod
    def _emit_tool_result(
        call: ToolCall,
        result: Any,
        *,
        emit: Callable[[AgentEvent], None],
    ) -> None:
        emit(
            AgentEvent(
                type="tool_result",
                payload={
                    "call_id": call.id,
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "output": result,
                    "status": "completed",
                },
            )
        )

    @staticmethod
    def _emit_tool_error(
        call: ToolCall,
        *,
        code: str,
        message: str,
        details: Any = None,
        output: Any = None,
        emit: Callable[[AgentEvent], None],
    ) -> dict[str, Any]:
        error = {"code": code[:64], "message": message}
        if details is not None:
            error["details"] = details
        observation = {
            "type": "tool_error",
            "call_id": call.id,
            "tool": call.name,
            "error": error,
            "trust": "untrusted_data_only",
        }
        emit(
            AgentEvent(
                type="tool_error",
                payload={
                    "call_id": call.id,
                    "tool_call_id": call.id,
                    "tool": call.name,
                    "output": output,
                    "status": "failed",
                    "error": observation["error"],
                },
            )
        )
        return observation

    @staticmethod
    def _call_key(tool_name: str, arguments: dict[str, Any]) -> str:
        return (
            tool_name
            + ":"
            + json.dumps(
                arguments,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            )
        )

    @staticmethod
    def _validate_schema(value: Any, schema: dict[str, Any], *, label: str) -> None:
        validate_parameters(value, schema, label=label)
