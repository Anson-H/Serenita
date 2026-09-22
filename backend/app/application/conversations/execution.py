"""Assemble the collaborators that execute one autonomous conversation turn."""

from typing import Any, Callable
from backend.app.core.cancellation import CancellationToken
from backend.app.agent_runtime.runtime import AgentHarnessRuntime
from backend.app.application.conversations.execution_preparation import (
    ConversationTurnPreparation,
)
from backend.app.application.conversations.execution_events import (
    ConversationExecutionEvents,
)
from backend.app.application.conversations.action_requests import (
    ConversationActionRequests,
)


class ConversationExecution:
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
        model_calls,
        compaction,
        guard,
        tool_results,
    ):
        self.repository = repository
        self.members = members
        self.paths = paths
        self.plugin_service = plugin_service
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
        cancellation_token: CancellationToken | None = None,
    ) -> dict[str, Any]:

        def check():
            self.guard.ensure_active(account_id, turn, cancellation_token)

        check()
        prepared = ConversationTurnPreparation(
            repository=self.repository,
            members=self.members,
            paths=self.paths,
            plugin_service=self.plugin_service,
            events=self.events,
            inputs=self.inputs,
            model_catalog=self.model_catalog,
            guard=self.guard,
        ).prepare(
            account_id,
            turn,
            user_message,
            on_workflow_event=on_workflow_event,
            cancellation_token=cancellation_token,
        )
        model_input = prepared.model_input
        requests = ConversationActionRequests(
            account_id=account_id,
            turn=turn,
            user_message=user_message,
            model_input=model_input,
            thinking_mode=prepared.thinking_mode,
            inputs=self.inputs,
            model_calls=self.model_calls,
            compaction=self.compaction,
            read_events=prepared.read_events,
            refresh_member=prepared.refresh_member,
            check=check,
            cancellation_token=cancellation_token,
        )
        events = ConversationExecutionEvents(
            repository=self.repository,
            events=self.events,
            tool_results=self.tool_results,
            account_id=account_id,
            turn=turn,
            user_message=user_message,
            model=lambda: model_input.model,
            check=check,
            on_workflow_event=on_workflow_event,
            cancellation_token=cancellation_token,
        )
        context_window, reserved_output = requests.context_budget()
        result = AgentHarnessRuntime(tool_registry=prepared.tools).execute(
            prepared.context,
            initial_skill_names=prepared.skill_names,
            on_event=events.handle,
            derive_messages=model_input.messages,
            complete_model=requests.complete,
            before_model_request=prepared.refresh_member,
            derive_skill_names=requests.skill_names,
            prepare_request=requests.prepare,
            before_tool_result=requests.prepare_tool_result,
            prepare_tool_result=model_input.prepare_tool_result,
            tool_result_context_budget=requests.context_budget,
            estimate_request_tokens=requests.estimate_tokens,
            context_window_tokens=context_window,
            reserved_output_tokens=reserved_output,
        )
        check()
        return {**result.output, "model_id": model_input.model["model_id"]}
