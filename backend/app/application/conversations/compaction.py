"""根据会话历史创建压缩检查点，并通过 Harness 回调重建模型请求。"""

import hashlib
import json
import math
import re
from backend.app.core.member_lifecycle import member_lifecycle_guard
from typing import Any, Callable


from backend.app.agent_runtime.model_types import (
    ModelRequest,
)
from backend.app.agent_runtime.compaction import (
    CompactionError,
    ContextBudget,
    public_message,
    select_history,
    split_summary_records,
    summarize_compaction,
    validate_tool_pairs,
)
from backend.app.application.model_provider_service import (
    ModelProviderService,
)
from backend.app.domain.conversations.model_history import derive_model_messages, tool_result_is_model_visible
from backend.app.domain.conversations.queries import current_session_turn_ids
from backend.app.core.tabular_json import decode_tabular_json, encode_tabular_json
from backend.app.core.cancellation import (
    CancellationToken,
)
from backend.app.core.time import local_now_iso
from backend.app.domain.model_capabilities import DEFAULT_CONTEXT_WINDOW_TOKENS
from backend.app.providers.errors import ProviderChatCompletionError
from backend.app.domain.conversations.events import make_event
from backend.app.storage.session_persistence import SessionEventWriteConflictError


now_iso = local_now_iso

DEFAULT_RESERVED_OUTPUT_TOKENS = 4096

ATTACHMENT_MIN_TOKEN_ESTIMATE = 512

ATTACHMENT_BYTES_PER_ESTIMATED_TOKEN = {
    "image": 128,
    "audio": 32,
    "video": 16,
    "file": 8,
}


class ConversationCompaction:
    def __init__(
        self,
        repository,
        model_catalog,
        paths,
        task_state,
        *,
        complete_model,
        ensure_active,
        thinking_mode_for_model,
    ):
        self.repository = repository
        self.model_catalog = model_catalog
        self.paths = paths
        self.task_state = task_state
        self.complete_model = complete_model
        self.ensure_active = ensure_active
        self.thinking_mode_for_model = thinking_mode_for_model

    @staticmethod
    def compaction_snapshot(events: list[Any]) -> str:
        relevant = [
            event.to_record()
            for event in events
            if event.type
            in {
                "turn/start",
                "turn/end",
                "user/message",
                "user/message-update",
                "assistant/message",
                "assistant/message-update",
                "tool/result",
                "harness/observation",
                "compaction/checkpoint",
            }
        ]
        return hashlib.sha256(
            json.dumps(relevant, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()

    def compact_model_request_if_needed(
        self,
        *,
        account_id: str,
        turn,
        user_message: dict[str, Any],
        model: dict[str, Any],
        model_request: ModelRequest,
        thinking_mode: str,
        rebuild_request: Callable[[list[Any]], ModelRequest] | None = None,
        cancellation_token: CancellationToken | None = None,
        force: bool = False,
        reason: str = "threshold",
        failed_fingerprints: set[str] | None = None,
        allow_pending: bool = False,
        snapshot_retries: int = 1,
    ) -> ModelRequest:
        self.ensure_active(account_id, turn, cancellation_token)
        if model_request.model_config.get("purpose") != "agent_action":
            return model_request
        budget = ContextBudget(
            int(model.get("context_window_tokens") or DEFAULT_CONTEXT_WINDOW_TOKENS),
            max(
                1,
                int(
                    model_request.model_config.get("max_output_tokens")
                    or model_request.model_config.get("max_tokens")
                    or model_request.model_config.get("max_completion_tokens")
                    or model.get("max_output_tokens")
                    or DEFAULT_RESERVED_OUTPUT_TOKENS
                ),
            ),
        )

        def estimate_action(request: ModelRequest) -> int:
            return self.estimate_model_request_tokens(
                ModelProviderService.prepare_transport_request(
                    model, request, thinking_mode
                )
            )

        estimated = estimate_action(model_request)
        if not force and estimated < budget.trigger:
            return model_request
        session_id = str(turn["session_id"])
        events = self.repository.session_events(account_id, session_id, repair=False)
        snapshot = self.compaction_snapshot(events)
        fingerprint_request = model_request.canonical_dict()
        # Advancing the request clock alone does not make a failed compaction
        # worth repeating. Keep dates, permissions, tools and all input intact.
        for section in model_request.context_sections:
            if section.context_type == "runtime_context":
                stable_section = re.sub(
                    r'"current_time"\s*:\s*"[^"]*"',
                    '"current_time":"<request-time>"',
                    section.content,
                )
                fingerprint_request["system"] = fingerprint_request["system"].replace(
                    section.content,
                    stable_section,
                )
        fingerprint = (
            snapshot
            + hashlib.sha256(
                json.dumps(fingerprint_request, sort_keys=True, default=str).encode()
            ).hexdigest()
        )
        if (
            failed_fingerprints is not None
            and fingerprint in failed_fingerprints
            and not force
        ):
            if estimated > budget.available:
                raise CompactionError("上下文超过硬限制，且相同上下文的压缩已经失败。")
            return model_request

        status_id = f"compaction_{self.repository.new_id()}"
        status_base = {
            "turn_id": str(turn["turn_id"]),
            "message_id": status_id,
            "reason": "overflow" if force else reason,
            "estimated_tokens_before": estimated,
            "target_tokens": budget.target,
        }

        def publish(status: str, **extra: Any) -> None:
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, session_id),
            ):
                self.ensure_active(account_id, turn, cancellation_token)
                self.repository.append_session_event(
                    account_id,
                    session_id,
                    "compaction/status",
                    {**status_base, "status": status, **extra},
                )

        def rebuild(candidate_events: list[Any]) -> ModelRequest:
            if rebuild_request is not None:
                return rebuild_request(candidate_events)
            # Non-runtime callers still use the same event projection. Carry
            # media parts separately so replacing their text cannot lose them.
            messages = derive_model_messages(
                candidate_events, current_turn_ids=[str(turn["turn_id"])]
            )
            media_parts = [
                part
                for message in model_request.messages
                if isinstance(message.get("content"), list)
                for part in message["content"]
                if isinstance(part, dict) and part.get("type") != "text"
            ]
            existing_parts = [
                part
                for message in messages
                if isinstance(message.get("content"), list)
                for part in message["content"]
                if isinstance(part, dict)
            ]
            unique_parts = []
            for part in media_parts:
                if part not in existing_parts and part not in unique_parts:
                    unique_parts.append(part)
            if unique_parts:
                messages.append({"role": "user", "content": unique_parts})
            return ModelRequest.build(
                system=model_request.system,
                messages=messages,
                tools=model_request.tools,
                context_sections=model_request.context_sections,
                tool_choice=model_request.tool_choice,
                model_config=model_request.model_config,
                transport_mode=model_request.transport_mode,
            )

        publish("running")
        try:
            surface = derive_model_messages(
                events,
                current_turn_ids=[str(turn["turn_id"])],
                include_surface_metadata=True,
            )
            validate_tool_pairs(
                [public_message(item) for item in surface],
                allow_pending=allow_pending,
            )
            user_seq = next(
                (
                    event.seq
                    for event in events
                    if event.type == "user/message"
                    and event.data.get("message_id") == user_message.get("message_id")
                ),
                None,
            )

            def estimate_messages(messages):
                return self.estimate_model_request_tokens(
                    ModelRequest.build(system="", messages=messages)
                )

            selected = select_history(
                surface,
                current_user_seq=user_seq,
                available_tokens=budget.available,
                estimate_messages=estimate_messages,
                force=force,
            )
            if not selected:
                raise CompactionError(
                    "没有可安全压缩的历史；当前输入、附件和最近行动已保留。"
                )
            sources = sorted({item["_source_seq"] for item in selected})
            source_set = set(sources)
            selected_events = [event for event in events if event.seq in source_set]
            selected_by_seq = {event.seq: event for event in selected_events}
            replaced_turns = set()
            for event in selected_events:
                if event.type == "compaction/checkpoint":
                    replaced_turns.update(event.data["replaced_turn_ids"])
                else:
                    replaced_turns.add(str(event.data["turn_id"]))
            active_turns = current_session_turn_ids(events) | {str(turn["turn_id"])}
            retained = self.unresolved_context_observations(
                events,
                compact_turns=active_turns,
                active_turns=active_turns,
            )
            # Only facts being removed (including facts carried by an older
            # checkpoint) need a separate exact copy.
            retained_call_ids = {
                str(event.data.get("call_id") or "")
                for event in events
                if event.type == "tool/result"
                and (
                    event.seq in sources
                    or not any(
                        message.get("_source_seq") == event.seq for message in surface
                    )
                )
            }
            retained = [
                item for item in retained if item["call_id"] in retained_call_ids
            ]
            previous = "\n\n".join(
                event.data["summary"]
                for event in selected_events
                if event.type == "compaction/checkpoint"
            )
            records = [
                {
                    "seq": item["_source_seq"],
                    "time": selected_by_seq[item["_source_seq"]].time,
                    "turn_id": selected_by_seq[item["_source_seq"]].data["turn_id"],
                    "message": public_message(item),
                }
                for item in selected
                if selected_by_seq[item["_source_seq"]].type != "compaction/checkpoint"
            ]
            history_records, prefix_records = split_summary_records(
                records, surface, source_set
            )
            checkpoint_data = {
                "turn_id": str(turn["turn_id"]),
                "message_id": status_id + "_summary",
                "compaction_id": status_id,
                "replaced_turn_ids": sorted(replaced_turns),
                "estimated_tokens_before": estimated,
                "target_tokens": budget.target,
                # Virtual projection only; replaced by the validated estimate
                # before this data can be committed to the event log.
                "estimated_tokens_after": 0,
            }
            operation = {
                "op": "replace",
                "start": min(item["_surface_seq"] for item in selected),
                "end": max(item["_surface_seq"] for item in selected) + 1,
            }

            def candidate(summary: str) -> tuple[ModelRequest, dict[str, Any]]:
                content = "<compacted-summary>\n" + summary + "\n</compacted-summary>"
                if retained:
                    content += (
                        "\n<unresolved-context-observations>\n"
                        + json.dumps(
                            retained, ensure_ascii=False, separators=(",", ":")
                        )
                        + "\n</unresolved-context-observations>"
                    )
                data = {**checkpoint_data, "summary": summary, "content": content}
                virtual = make_event(
                    "compaction/checkpoint",
                    events[-1].seq + 1 if events else 0,
                    data,
                    source_event_seqs=sources,
                    surface_op=operation,
                )
                return rebuild([*events, virtual]), data

            minimum, _ = candidate("…")
            if estimate_action(minimum) > budget.target:
                raise CompactionError(
                    "必须保留的当前输入、附件、工具调用组或结构化内容已超过压缩目标预算。"
                )

            compact_model = (
                self.model_catalog.default_model_for_account(account_id, "compact")
                or model
            )
            compact_window = int(
                compact_model.get("context_window_tokens")
                or DEFAULT_CONTEXT_WINDOW_TOKENS
            )
            compact_output = min(
                DEFAULT_RESERVED_OUTPUT_TOKENS,
                int(
                    compact_model.get("max_output_tokens")
                    or DEFAULT_RESERVED_OUTPUT_TOKENS
                ),
                max(1, compact_window // 4),
            )
            summary_budget = ContextBudget(compact_window, compact_output)

            def complete(request: ModelRequest):
                self.ensure_active(account_id, turn, cancellation_token)
                return self.complete_model(
                    account_id=account_id,
                    turn=turn,
                    user_message=user_message,
                    model=compact_model,
                    model_request=request,
                    thinking_mode=self.thinking_mode_for_model(
                        compact_model, "default"
                    ),
                    purpose="context_compaction",
                    timeout_seconds=90,
                    cancellation_token=cancellation_token,
                )

            summary = summarize_compaction(
                history_records,
                prefix_records,
                previous_summary=previous,
                budget=summary_budget,
                estimate=self.estimate_model_request_tokens,
                complete=complete,
            )
            rebuilt, data = candidate(summary.render())
            after = estimate_action(rebuilt)
            if after > budget.target or after >= estimated:
                summary = summarize_compaction(
                    [],
                    [],
                    previous_summary="",
                    budget=summary_budget,
                    estimate=self.estimate_model_request_tokens,
                    complete=complete,
                    tighten=summary,
                )
                rebuilt, data = candidate(summary.render())
                after = estimate_action(rebuilt)
            if after > budget.target or after >= estimated:
                raise CompactionError("压缩摘要未达到目标预算，原上下文已保留。")
            validate_tool_pairs(rebuilt.messages, allow_pending=allow_pending)
            data["estimated_tokens_after"] = after
            with (
                member_lifecycle_guard(paths=self.paths),
                self.task_state.session_lock(account_id, session_id),
            ):
                self.ensure_active(account_id, turn, cancellation_token)
                live_events = self.repository.session_events(
                    account_id, session_id, repair=False
                )
                if self.compaction_snapshot(live_events) != snapshot:
                    raise CompactionError(
                        "摘要生成期间上下文已变化，候选摘要已丢弃。",
                        code="CONTEXT_COMPACTION_STALE",
                    )
                # Revalidate dynamic system metadata/permission-dependent tools.
                live_candidate = make_event(
                    "compaction/checkpoint",
                    live_events[-1].seq + 1,
                    data,
                    source_event_seqs=sources,
                    surface_op=operation,
                )
                live_request = rebuild([*live_events, live_candidate])
                if live_request.canonical_dict() != rebuilt.canonical_dict():
                    raise CompactionError(
                        "摘要生成期间请求装配已变化，候选摘要已丢弃。",
                        code="CONTEXT_COMPACTION_STALE",
                    )
                self.repository.append_session_events(
                    account_id,
                    session_id,
                    [
                        {
                            "type": "compaction/checkpoint",
                            "data": data,
                            "source_event_seqs": sources,
                            "surface_op": operation,
                        },
                        {
                            "type": "compaction/status",
                            "data": {
                                **status_base,
                                "status": "completed",
                                "estimated_tokens_after": after,
                            },
                        },
                    ],
                    expected_seq=live_events[-1].seq + 1,
                )
            return rebuilt
        except (ProviderChatCompletionError, SessionEventWriteConflictError) as exc:
            if failed_fingerprints is not None:
                failed_fingerprints.add(fingerprint)
            publish(
                "failed",
                error={"code": "CONTEXT_COMPACTION_FAILED", "message": str(exc)},
            )
            if getattr(exc, "code", None) == "CONTEXT_COMPACTION_STALE" or isinstance(
                exc, SessionEventWriteConflictError
            ):
                if snapshot_retries <= 0:
                    raise CompactionError(
                        "上下文持续变化，压缩未提交，请重新发送当前请求。",
                        code="CONTEXT_COMPACTION_STALE",
                    ) from exc
                fresh = rebuild(
                    self.repository.session_events(account_id, session_id, repair=False)
                )
                return self.compact_model_request_if_needed(
                    account_id=account_id,
                    turn=turn,
                    user_message=user_message,
                    model=model,
                    model_request=fresh,
                    thinking_mode=thinking_mode,
                    rebuild_request=rebuild_request,
                    cancellation_token=cancellation_token,
                    force=force,
                    reason=reason,
                    failed_fingerprints=failed_fingerprints,
                    allow_pending=allow_pending,
                    snapshot_retries=snapshot_retries - 1,
                )
            if force or estimated > budget.available:
                raise CompactionError(str(exc)) from exc
            return model_request

    @staticmethod
    def unresolved_context_observations(
        events: list[Any],
        *,
        compact_turns: set[str],
        active_turns: set[str],
    ) -> list[dict[str, Any]]:
        """Apply generic Tool effects to retain exact unresolved Observation items."""

        handled: set[tuple[str, int]] = set()
        for event in events:
            turn_id = str(event.data.get("turn_id") or "")
            if turn_id not in active_turns:
                continue
            if event.type != "tool/result":
                continue
            if str(event.data.get("status") or "") == "completed":
                result = event.data.get("result")
                effects = result.get("effects") if isinstance(result, dict) else None
            else:
                error = event.data.get("error") or {}
                details = error.get("details") or {}
                effects = (
                    details.get("effects")
                    if details.get("execution_completed") is True
                    else None
                )
            if not isinstance(effects, dict):
                continue
            references = effects.get("resolved_context_items")
            if not isinstance(references, list):
                continue
            for reference in references:
                if not isinstance(reference, dict):
                    continue
                call_id = str(reference.get("call_id") or "")
                index = reference.get("index")
                if call_id and isinstance(index, int):
                    handled.add((call_id, index))

        retained: list[dict[str, Any]] = []
        for event in events:
            if event.type != "tool/result":
                continue
            if str(event.data.get("turn_id") or "") not in compact_turns:
                continue
            if not tool_result_is_model_visible(event.data):
                continue
            call_id = str(event.data.get("call_id") or "")
            result = event.data.get("result")
            if not isinstance(result, dict):
                continue
            output = result.get("output")
            if result.get("type") != "tool_result" or not isinstance(output, dict):
                continue
            output = decode_tabular_json(output)
            effects = result.get("effects")
            retention = (
                effects.get("context_retention") if isinstance(effects, dict) else None
            )
            if not isinstance(retention, dict):
                continue
            collection_field = str(retention.get("collection_field") or "")
            index_field = str(retention.get("index_field") or "")
            collection = output.get(collection_field)
            if (
                not collection_field
                or not index_field
                or not isinstance(collection, list)
            ):
                continue
            unresolved = [
                item
                for item in collection
                if isinstance(item, dict)
                and isinstance(item.get(index_field), int)
                and (call_id, int(item[index_field])) not in handled
            ]
            if unresolved:
                retained_output = dict(output)
                retained_output[collection_field] = unresolved
                retained.append(
                    {
                        "call_id": call_id,
                        "tool_name": str(
                            event.data.get("name") or result.get("name") or ""
                        ),
                        "output": encode_tabular_json(retained_output),
                    }
                )
        return retained

    @classmethod
    def estimate_model_request_tokens(cls, model_request: ModelRequest) -> int:
        projected, attachment_tokens = cls.token_estimation_projection(
            model_request.canonical_dict()
        )
        encoded = json.dumps(
            projected,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return max(1, math.ceil(len(encoded) / 4) + attachment_tokens)

    @classmethod
    def token_estimation_projection(cls, value: Any) -> tuple[Any, int]:
        """Remove transport encoding overhead while retaining media budget.

        Provider-native attachments are carried as Base64 on the wire, but the
        model does not tokenize that Base64 as ordinary prompt text. Counting
        the encoded bytes at the text ratio can make a single image appear to
        consume an entire context window. Media still receives a conservative
        type-specific estimate so attachment-heavy requests remain bounded.
        """

        if isinstance(value, list):
            projected: list[Any] = []
            attachment_tokens = 0
            for item in value:
                normalized, tokens = cls.token_estimation_projection(item)
                projected.append(normalized)
                attachment_tokens += tokens
            return projected, attachment_tokens
        if not isinstance(value, dict):
            return value, 0

        part_type = str(value.get("type") or "file").lower()
        bytes_per_token = ATTACHMENT_BYTES_PER_ESTIMATED_TOKEN.get(
            part_type,
            ATTACHMENT_BYTES_PER_ESTIMATED_TOKEN["file"],
        )
        projected_dict: dict[str, Any] = {}
        attachment_tokens = 0
        for key, item in value.items():
            if key == "data_base64" and isinstance(item, str):
                encoded_length = len(item.strip())
                decoded_bytes = math.ceil(encoded_length * 3 / 4)
                attachment_tokens += max(
                    ATTACHMENT_MIN_TOKEN_ESTIMATE,
                    math.ceil(decoded_bytes / bytes_per_token),
                )
                projected_dict[key] = (
                    f"<provider-native-{part_type}:{decoded_bytes}-bytes>"
                )
                continue
            normalized, tokens = cls.token_estimation_projection(item)
            projected_dict[key] = normalized
            attachment_tokens += tokens
        return projected_dict, attachment_tokens
