"""Prepare, compact and execute model requests within one turn's existing budget."""

from backend.app.agent_runtime.compaction import CompactionError
from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.agent_runtime.runtime import RequestRebuilder
from backend.app.application.models.provider_service import ModelProviderService
from backend.app.application.conversations.compaction import (
    DEFAULT_RESERVED_OUTPUT_TOKENS,
)
from backend.app.domain.conversations.model_history import visible_loaded_skill_names
from backend.app.domain.model_capabilities import DEFAULT_CONTEXT_WINDOW_TOKENS


class ConversationActionRequests:
    def __init__(
        self,
        *,
        account_id,
        turn,
        user_message,
        model_input,
        thinking_mode,
        inputs,
        model_calls,
        compaction,
        read_events,
        refresh_member,
        check,
        cancellation_token,
    ):
        self.account_id, self.turn, self.turn_id = (
            account_id,
            turn,
            str(turn["turn_id"]),
        )
        self.user_message, self.model_input, self.thinking_mode = (
            user_message,
            model_input,
            thinking_mode,
        )
        self.inputs, self.model_calls, self.compaction = (
            inputs,
            model_calls,
            compaction,
        )
        self.read_events, self.refresh_member, self.check = (
            read_events,
            refresh_member,
            check,
        )
        self.cancellation_token, self.failed_compactions = (cancellation_token, set())

    def context_budget(self):
        model = self.model_input.model
        return (
            int(model.get("context_window_tokens") or DEFAULT_CONTEXT_WINDOW_TOKENS),
            int(model.get("max_output_tokens") or DEFAULT_RESERVED_OUTPUT_TOKENS),
        )

    def estimate_tokens(self, request):
        model = self.model_input.model
        prepared = ModelProviderService.prepare_transport_request(
            model, request, self.thinking_mode
        )
        return self.compaction.estimate_model_request_tokens(prepared, model=model)

    def prepare_tool_result(self, request, rebuild):
        return self.prepare(request, rebuild, tool_result=True)

    def complete(self, request: ModelRequest):
        self.check()
        return self.model_calls.complete_chat_with_events(
            account_id=self.account_id,
            turn=self.turn,
            user_message=self.user_message,
            model=self.model_input.model,
            model_request=request,
            thinking_mode=self.inputs.thinking_mode_for_model(
                self.model_input.model, self.thinking_mode
            ),
            purpose="agent_action",
            timeout_seconds=90,
            cancellation_token=self.cancellation_token,
        )

    def skill_names(self):
        return visible_loaded_skill_names(
            list(self.read_events().events), current_turn_ids=[self.turn_id]
        )

    def prepare(
        self,
        request: ModelRequest,
        rebuild_request: RequestRebuilder,
        force: bool = False,
        *,
        tool_result: bool = False,
    ):
        self.refresh_member()

        def rebuild(surface_events):
            self.refresh_member()
            return rebuild_request(
                messages=self.model_input.messages(surface_events),
                skill_names=visible_loaded_skill_names(
                    surface_events, current_turn_ids=[self.turn_id]
                ),
            )

        try:
            return self.compaction.compact_model_request_if_needed(
                account_id=self.account_id,
                turn=self.turn,
                user_message=self.user_message,
                model=self.model_input.model,
                model_request=request,
                thinking_mode=self.thinking_mode,
                rebuild_request=rebuild,
                cancellation_token=self.cancellation_token,
                force=force,
                reason="tool_result" if tool_result else "threshold",
                failed_fingerprints=self.failed_compactions,
                allow_pending=tool_result,
            )
        except CompactionError:
            if tool_result:
                return request
            raise
