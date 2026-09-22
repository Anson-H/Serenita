"""调用模型并保存会话请求、流式内容、工具请求、用量和结束状态。"""

from backend.app.core.time import elapsed_ms
import time
from backend.app.core.runtime.member_lifecycle import member_lifecycle_guard
from typing import Any, Callable


from backend.app.agent_runtime.model_types import (
    AssistantModelOutput,
    ModelRequest,
)
from backend.app.core.cancellation import (
    CancellationToken,
    OperationCancelledError,
)
from backend.app.core.time import local_now_iso
from backend.app.core.model_retry import (
    MAX_MODEL_ATTEMPTS,
    MODEL_RETRY_DELAY_SECONDS,
    current_retry_attempt,
    error_details,
    run_model_request,
)
from backend.app.providers.responses import parse_tool_calls
from backend.app.providers.errors import ProviderChatCompletionError


from backend.app.application.conversations.request_audit import ModelRequestAudit

now_iso = local_now_iso


class ModelCallRecorder:
    def __init__(
        self,
        repository,
        model_catalog,
        paths,
        task_state,
        *,
        ensure_active,
        next_model_step,
        check_resources=None,
    ):
        self.repository = repository
        self.model_catalog = model_catalog
        self.paths = paths
        self.task_state = task_state
        self.ensure_active = ensure_active
        self.next_model_step = next_model_step
        self.audit = ModelRequestAudit()
        self.check_resources = check_resources

    def complete_chat_with_events(
        self,
        *,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        model: dict[str, Any],
        model_request: ModelRequest,
        thinking_mode: str,
        purpose: str,
        timeout_seconds: float | None = None,
        on_content_delta: Callable[[str], None] | None = None,
        cancellation_token: CancellationToken | None = None,
    ) -> Any:
        self.ensure_active(account_id, turn, cancellation_token)
        prepared_request = self.model_catalog.prepare_stream_chat_for_account(
            account_id=account_id,
            model=model,
            model_request=model_request,
            thinking_mode=thinking_mode,
        )
        first_call_id = self.repository.new_id()
        state = {"call_id": first_call_id, "step": 0, "attempt": 1}

        def check():
            self.ensure_active(account_id, turn, cancellation_token)

        def retry_metadata(status):
            return {
                "attempt": state["attempt"],
                "max_attempts": MAX_MODEL_ATTEMPTS,
                "delay_seconds": MODEL_RETRY_DELAY_SECONDS
                if status == "waiting"
                else 0,
                "status": status,
            }

        def record_retry(status, error=None):
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, turn["session_id"]),
            ):
                check()
                self.repository.append_session_event(
                    account_id,
                    turn["session_id"],
                    "model/retry",
                    {
                        "turn_id": turn["turn_id"],
                        "step": state["step"],
                        "call_id": state["call_id"],
                        "first_call_id": first_call_id,
                        "retry": retry_metadata(status),
                        "created_at": now_iso(),
                        **(
                            {"error": error_details(error)} if error is not None else {}
                        ),
                    },
                )

        def invoke():
            check()
            ensure_model = getattr(self.model_catalog, "ensure_model_available", None)
            if ensure_model is not None:
                ensure_model(account_id, model)
            if self.check_resources is not None:
                self.check_resources(
                    account_id,
                    str(turn["session_id"]),
                    list(user_message.get("context_resources") or []),
                    model,
                )
            state["attempt"] = current_retry_attempt()
            state["call_id"] = (
                first_call_id if state["attempt"] == 1 else self.repository.new_id()
            )
            state["step"] = self.next_model_step(account_id, turn)
            record_retry("running")
            chunks = self.stream_chat_with_events(
                account_id=account_id,
                turn=turn,
                user_message=user_message,
                model=model,
                model_request=model_request,
                thinking_mode=thinking_mode,
                purpose=purpose,
                timeout_seconds=timeout_seconds,
                cancellation_token=cancellation_token,
                prepared_request=prepared_request,
                call_id=state["call_id"],
                step=state["step"],
                retry=retry_metadata("running"),
                first_call_id=first_call_id,
            )
            # Execution records remain live. Consumers receive only one successful
            # response; fragments from an interrupted attempt never become input.
            try:
                while True:
                    try:
                        next(chunks)
                    except StopIteration as completed:
                        return completed.value
            finally:
                chunks.close()

        try:
            output = run_model_request(
                invoke,
                check_running=check,
                cancellation_token=cancellation_token,
                on_retry=lambda error, attempt: record_retry("waiting", error),
            )
        except OperationCancelledError:
            raise
        except Exception as error:
            record_retry("failed", error)
            raise
        record_retry("completed")
        if on_content_delta is not None and output.content:
            on_content_delta(output.content)
        return output

    def stream_chat_with_events(
        self,
        *,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        model: dict[str, Any],
        model_request: ModelRequest,
        thinking_mode: str,
        purpose: str,
        timeout_seconds: float | None = None,
        cancellation_token: CancellationToken | None = None,
        prepared_request=None,
        call_id: str | None = None,
        step: int | None = None,
        retry: dict | None = None,
        first_call_id: str | None = None,
    ) -> Any:
        """Persist one model call and yield its chunks to the Harness."""

        def append_active_event(*args, **kwargs):
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, turn["session_id"]),
            ):
                self.ensure_active(account_id, turn, cancellation_token)
                return self.repository.append_session_event(*args, **kwargs)

        def append_active_events(*args, **kwargs):
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, turn["session_id"]),
            ):
                self.ensure_active(account_id, turn, cancellation_token)
                return self.repository.append_session_events(*args, **kwargs)

        self.ensure_active(account_id, turn, cancellation_token)
        call_id = call_id or self.repository.new_id()
        step = step if step is not None else self.next_model_step(account_id, turn)
        started_at = time.monotonic()
        prepared_request = (
            prepared_request
            or self.model_catalog.prepare_stream_chat_for_account(
                account_id=account_id,
                model=model,
                model_request=model_request,
                thinking_mode=thinking_mode,
            )
        )
        durable_provider_payload = self.audit.redact_provider_payload(
            prepared_request.provider_payload
        )
        if not isinstance(durable_provider_payload, dict):
            raise ValueError("Provider payload 必须是 JSON 对象。")
        self.ensure_active(account_id, turn, cancellation_token)
        append_active_events(
            account_id,
            turn["session_id"],
            self.audit.request_event_specifications(
                turn=turn,
                call_id=call_id,
                purpose=purpose,
                model=model,
                model_request=model_request,
                thinking_mode=thinking_mode,
                step=step,
                prepared_request=prepared_request,
                durable_provider_payload=durable_provider_payload,
                retry=retry,
                first_call_id=first_call_id,
            ),
        )
        reasoning_parts: list[str] = []
        content_parts: list[str] = []
        raw_content_parts: list[str] = []
        tool_call_parts: dict[int, dict[str, str]] = {}
        channel_first: dict[str, float] = {}
        channel_last: dict[str, float] = {}
        active_channel: str | None = None
        usage: dict[str, Any] = {}
        stop_reason = ""
        created_at = now_iso()

        def note_channel(channel: str, now: float) -> None:
            if channel not in channel_first:
                channel_first[channel] = now
            channel_last[channel] = now

        def channel_durations_ms() -> dict[str, int]:
            return {
                channel: elapsed_ms(channel_first[channel], channel_last[channel])
                for channel in ("reasoning", "content", "raw_output", "tool_request")
                if channel in channel_first
            }

        def write_chunk(chunk: dict[str, Any], duration_ms: int) -> None:
            self.ensure_active(account_id, turn, cancellation_token)
            append_active_event(
                account_id=account_id,
                session_id=turn["session_id"],
                event_type="assistant/chunk",
                data={
                    "turn_id": turn["turn_id"],
                    "step": step,
                    "call_id": call_id,
                    "message_id": f"model_{call_id}",
                    "branch_addressable": False,
                    "purpose": purpose,
                    "parent_message_id": user_message.get("message_id"),
                    "model_id": model.get("model_id"),
                    "duration_ms": duration_ms,
                    "created_at": created_at,
                    "chunk": chunk,
                },
            )

        def append_chunk(chunk: dict[str, Any], *, channel: str | None = None) -> None:
            nonlocal active_channel
            now = time.monotonic()
            if channel is not None:
                if (
                    active_channel is not None
                    and active_channel != channel
                    and active_channel != "tool_request"
                ):
                    note_channel(active_channel, now)
                    write_chunk(
                        {"type": "channel-end", "channel": active_channel},
                        elapsed_ms(channel_first[active_channel], now),
                    )
                note_channel(channel, now)
                active_channel = channel
                duration_ms = elapsed_ms(channel_first[channel], now)
            else:
                duration_ms = elapsed_ms(started_at, now)
            write_chunk(chunk, duration_ms)

        chunks = None
        try:
            chunks = self.model_catalog.stream_prepared_chat_for_account(
                prepared_request=prepared_request,
                timeout_seconds=timeout_seconds,
                cancellation_token=cancellation_token,
            )
            for chunk in chunks:
                self.ensure_active(account_id, turn, cancellation_token)
                if chunk.reasoning_delta:
                    reasoning_parts.append(chunk.reasoning_delta)
                    append_chunk(
                        {"type": "reasoning-delta", "delta": chunk.reasoning_delta},
                        channel="reasoning",
                    )
                if chunk.content_delta:
                    content_parts.append(chunk.content_delta)
                    append_chunk(
                        {"type": "text-delta", "delta": chunk.content_delta},
                        channel="content",
                    )
                if chunk.raw_content_delta:
                    raw_content_parts.append(chunk.raw_content_delta)
                    append_chunk(
                        {
                            "type": "raw-text-delta",
                            "delta": chunk.raw_content_delta,
                        },
                        channel="raw_output",
                    )
                for delta in chunk.tool_call_deltas:
                    part = tool_call_parts.setdefault(
                        delta.index,
                        {"id": "", "name": "", "arguments": ""},
                    )
                    if delta.id:
                        part["id"] = delta.id
                    part["name"] += delta.name_delta
                    part["arguments"] += delta.arguments_delta
                    append_chunk(
                        {
                            "type": "tool-call-delta",
                            "index": delta.index,
                            "id": delta.id,
                            "name_delta": delta.name_delta,
                            "arguments_delta": delta.arguments_delta,
                        },
                        channel="tool_request",
                    )
                if chunk.usage:
                    usage.update(chunk.usage)
                    append_chunk({"type": "usage", "usage": dict(chunk.usage)})
                if chunk.stop_reason:
                    stop_reason = chunk.stop_reason
                    append_chunk({"type": "stop", "reason": chunk.stop_reason})
                yield chunk
            if active_channel is not None:
                note_channel(active_channel, time.monotonic())
            if not stop_reason:
                raise ProviderChatCompletionError(
                    "模型响应在收到结束标记前中断。", code="MODEL_STREAM_INCOMPLETE"
                )
            # Assemble calls here; rejected argument text reaches the Harness
            # for a tool error and the model's next action.
            tool_calls = parse_tool_calls(
                [
                    {
                        "id": tool_call_parts[index]["id"],
                        "function": {
                            "name": tool_call_parts[index]["name"],
                            "arguments": tool_call_parts[index]["arguments"],
                        },
                    }
                    for index in sorted(tool_call_parts)
                ]
            )
        except OperationCancelledError:
            if active_channel is not None:
                note_channel(active_channel, time.monotonic())
            raise
        except Exception as exc:
            if active_channel is not None:
                note_channel(active_channel, time.monotonic())
            failed_result = {
                "content": "".join(content_parts),
                "raw_content": "".join(raw_content_parts),
                "reasoning": "".join(reasoning_parts),
                "tool_calls": [],
                "usage": usage,
                "stop_reason": "error",
            }
            append_active_event(
                account_id,
                turn["session_id"],
                "model/result",
                {
                    "turn_id": turn["turn_id"],
                    "step": step,
                    "call_id": call_id,
                    "status": "failed",
                    "result": failed_result,
                    "duration_ms": elapsed_ms(started_at, time.monotonic()),
                    "channel_durations_ms": channel_durations_ms(),
                    "created_at": now_iso(),
                    "started_at": created_at,
                    **(
                        {
                            "retry": {**retry, "status": "failed"},
                            "first_call_id": first_call_id,
                        }
                        if retry
                        else {}
                    ),
                    "error": error_details(exc),
                },
            )
            append_active_event(
                account_id,
                turn["session_id"],
                "step/end",
                {
                    "turn_id": turn["turn_id"],
                    "step": step,
                    "status": "failed",
                },
            )
            raise
        finally:
            close_stream = getattr(chunks, "close", None)
            if callable(close_stream):
                close_stream()

        self.ensure_active(account_id, turn, cancellation_token)
        content = "".join(content_parts)
        raw_content = "".join(raw_content_parts)
        reasoning = "".join(reasoning_parts)
        self.ensure_active(account_id, turn, cancellation_token)
        duration_ms = elapsed_ms(started_at, time.monotonic())
        append_active_event(
            account_id,
            turn["session_id"],
            "model/result",
            {
                "turn_id": turn["turn_id"],
                "step": step,
                "call_id": call_id,
                "status": "completed",
                "duration_ms": duration_ms,
                "channel_durations_ms": channel_durations_ms(),
                "created_at": now_iso(),
                "started_at": created_at,
                **(
                    {
                        "retry": {**retry, "status": "completed"},
                        "first_call_id": first_call_id,
                    }
                    if retry
                    else {}
                ),
                "result": {
                    "content": content,
                    "raw_content": raw_content,
                    "reasoning": reasoning,
                    "tool_calls": [
                        {
                            "id": tool_call_parts[index]["id"],
                            "type": "function",
                            "function": {
                                "name": tool_call_parts[index]["name"],
                                "arguments": tool_call_parts[index]["arguments"],
                            },
                        }
                        for index in sorted(tool_call_parts)
                    ],
                    "usage": usage,
                    "stop_reason": stop_reason,
                },
            },
        )
        append_active_event(
            account_id,
            turn["session_id"],
            "step/end",
            {
                "turn_id": turn["turn_id"],
                "step": step,
                "status": "completed",
            },
        )
        return AssistantModelOutput(
            content=content,
            reasoning=reasoning,
            tool_calls=tuple(tool_calls),
            usage=usage,
            stop_reason=stop_reason,
            raw_content=raw_content,
        )
