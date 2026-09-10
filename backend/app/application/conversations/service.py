"""装配会话组件，为 HTTP 接口和其他应用服务提供明确的公开操作。"""

from backend.app.application.conversations.execution import ConversationExecution
from backend.app.application.conversations.tool_results import ConversationToolResults
from backend.app.application.conversations.access import ConversationExecutionGuard
from backend.app.application.conversations.inputs import ConversationInputs
from backend.app.application.conversations.events import ConversationEvents
from backend.app.application.conversations.model_calls import ModelCallRecorder
from backend.app.application.conversations.compaction import ConversationCompaction
from backend.app.application.conversations.jobs import ConversationTurnJobs
from backend.app.application.conversations.queue import ConversationQueue, ConversationQueueActions
from backend.app.application.conversations.sse import ConversationSSESubscriber
from backend.app.application.conversations.titles import ConversationTitleTasks
from backend.app.storage.paths import app_paths
from backend.app.repositories.member_repository import MemberRepository
from typing import Any, Mapping, Optional
from backend.app.core.cancellation import CancellationToken
from backend.app.domain.conversations.events import SessionEvent
from backend.app.application.model_provider_service import ModelProviderService
from backend.app.core.conversation_tasks import tasks_for_paths
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.application.conversations.submissions import ConversationSubmissions
from backend.app.application.conversations.lifecycle import ConversationTurnLifecycle
from backend.app.application.conversations.queries import ConversationQueries
from backend.app.application.conversations.sessions import ConversationSessionCommands


class ConversationService:
    """Compose conversation capabilities and expose user operations."""
    def __init__(
        self,
        repository: ConversationRepository | None = None,
        model_catalog: ModelProviderService | None = None,
        *,
        paths=None,
        members=None,
        services=None,
    ):
        self.paths = paths or getattr(repository, "paths", None) or app_paths()
        self.members = members or MemberRepository(paths=self.paths)
        if services is None:
            from backend.app.application.services import ApplicationServices

            services = ApplicationServices(self.paths, members=self.members)
        self.services = services
        self.task_state = tasks_for_paths(self.paths)
        self.repository = repository or ConversationRepository(
            paths=self.paths, members=self.members
        )
        self.events = ConversationEvents(self.repository)
        self.model_catalog = model_catalog or ModelProviderService(paths=self.paths)
        self.inputs = ConversationInputs(
            self.repository,
            self.members,
            self.model_catalog,
            self.services,
            self.events,
        )
        self.guard = ConversationExecutionGuard(self.repository, self.members)
        self.tool_results = ConversationToolResults(
            self.repository, self.events, self.task_state, self.paths, self.guard
        )

        def next_model_step(account_id: str, turn: Mapping[str, Any]) -> int:
            return self.events.current_model_step(account_id, turn) + 1

        self.model_calls = ModelCallRecorder(
            self.repository,
            self.model_catalog,
            self.paths,
            self.task_state,
            ensure_active=self.guard.ensure_active,
            next_model_step=next_model_step,
        )
        self.compaction = ConversationCompaction(
            self.repository,
            self.model_catalog,
            self.paths,
            self.task_state,
            complete_model=self.model_calls.complete_chat_with_events,
            ensure_active=self.guard.ensure_active,
            thinking_mode_for_model=self.inputs.thinking_mode_for_model,
        )
        self.execution = ConversationExecution(
            repository=self.repository,
            members=self.members,
            paths=self.paths,
            services=self.services,
            events=self.events,
            inputs=self.inputs,
            model_catalog=self.model_catalog,
            model_calls=self.model_calls,
            compaction=self.compaction,
            guard=self.guard,
            tool_results=self.tool_results,
        )
        self.titles = ConversationTitleTasks(
            self.repository,
            self.model_catalog,
            self.task_state,
            prepare_attachments=self.inputs.model_and_attachment_parts,
            prepare_request=self.inputs.model_request_from_messages,
        )

        # These callbacks run only after construction. Their signatures make
        # the jobs/lifecycle and queue/submissions connections explicit.
        def execute_turn(
            account_id: str,
            turn: Mapping[str, Any],
            messages_by_id: dict[str, dict[str, Any]],
            *,
            cancellation_token: CancellationToken | None = None,
        ) -> None:
            self.lifecycle.execute_turn(
                account_id, turn, messages_by_id,
                cancellation_token=cancellation_token,
            )

        def record_turn_failure(
            account_id: str, turn: Mapping[str, Any], code: str, message: str
        ) -> None:
            self.lifecycle.record_turn_failure(account_id, turn, code, message)

        def promote_next(account_id: str, session_id: str) -> dict[str, Any] | None:
            return self.queue.promote_next(account_id, session_id)

        def start_message_turn(
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
        ) -> dict[str, Any]:
            return self.submissions.start_message_turn(
                account_id=account_id,
                session_id=session_id,
                raw_text=raw_text,
                model_id=model_id,
                thinking_mode=thinking_mode,
                context_resources=context_resources,
                attach_resources=attach_resources,
                current_events=current_events,
                expected_seq=expected_seq,
                queued_input_id=queued_input_id,
            )

        self.jobs = ConversationTurnJobs(
            self.repository,
            self.task_state,
            self.titles,
            execute_turn=execute_turn,
            record_failure=record_turn_failure,
            promote_next=promote_next,
        )
        self.queries = ConversationQueries(
            repository=self.repository, members=self.members,
            events=self.events, services=self.services,
        )
        self.queue = ConversationQueue(
            self.repository,
            self.paths,
            self.members,
            self.task_state,
            ConversationQueueActions(
                member_accessible=self.queries.member_accessible,
                start_message=start_message_turn,
                start_job=self.jobs.start,
                cancel_turn=self.cancel_turn,
                get_turn=self.queries.get_turn,
                member_access=self.queries.member_access,
                current_records=self.queries.current_records,
                drain_cleanup=self.inputs.drain_attachment_cleanup,
            ),
        )
        self.submissions = ConversationSubmissions(
            repository=self.repository, paths=self.paths, members=self.members,
            events=self.events, inputs=self.inputs, task_state=self.task_state,
            titles=self.titles, queue=self.queue, queries=self.queries,
        )
        self.lifecycle = ConversationTurnLifecycle(
            repository=self.repository, paths=self.paths, events=self.events,
            execution=self.execution, guard=self.guard, jobs=self.jobs,
            queue=self.queue, task_state=self.task_state, queries=self.queries,
            notifications=self.services.notifications,
        )
        self.sessions = ConversationSessionCommands(
            repository=self.repository, paths=self.paths, events=self.events,
            inputs=self.inputs, jobs=self.jobs, task_state=self.task_state,
            titles=self.titles, queries=self.queries,
        )
        self.streams = ConversationSSESubscriber(
            self.repository, self.task_state.notifications,
            interrupt_expired_jobs=self.lifecycle.interrupt_expired_turn_jobs,
        )

    def start_turn_job(self, account_id: str, session_id: str, stream_id: str) -> None:
        return self.jobs.start(account_id, session_id, stream_id)


    def wait_for_turn_job(
        self,
        account_id: str,
        session_id: str,
        stream_id: str,
        timeout: float = 2.0,
    ) -> None:
        return self.jobs.wait(account_id, session_id, stream_id, timeout)


    def reorder_queued_inputs(
        self, account_id: str, session_id: str, input_ids: list[str]
    ) -> dict[str, Any]:
        return self.queue.reorder(account_id, session_id, input_ids)


    def remove_queued_input(
        self,
        account_id: str,
        session_id: str,
        input_id: str,
        *,
        restore_to_draft: bool = False,
    ) -> dict[str, Any]:
        return self.queue.remove(
            account_id, session_id, input_id, restore_to_draft=restore_to_draft
        )


    def run_queued_input_now(
        self, account_id: str, session_id: str, input_id: str
    ) -> dict[str, Any]:
        return self.queue.run_now(account_id, session_id, input_id)


    def stream_events(self, account_id: str, session_id: str, stream_id: str):
        return self.streams.stream_events(account_id, session_id, stream_id)


    def cancel_title_generation(self, account_id: str, session_id: str) -> bool:
        return self.titles.cancel(account_id, session_id)


    def wait_for_all_jobs(self, timeout: float = 2.0) -> None:
        self.task_state.wait(timeout)


    def send_message(
        self,
        account_id: str,
        session_id: Optional[str],
        raw_text: str,
        model_id: Optional[str],
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
        *,
        member_id: str | None,
    ) -> dict[str, Any]:
        return self.submissions.send_message(account_id, session_id, raw_text, model_id, thinking_mode, context_resources, member_id=member_id)

    def regenerate_message(
        self,
        account_id: str,
        session_id: str,
        message_id: str,
        model_id: Optional[str] = None,
        thinking_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        return self.submissions.regenerate_message(account_id, session_id, message_id, model_id, thinking_mode)

    def edit_message(
        self,
        account_id: str,
        session_id: str,
        message_id: str,
        raw_text: str,
        model_id: Optional[str],
        thinking_mode: str,
        context_resources: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return self.submissions.edit_message(account_id, session_id, message_id, raw_text, model_id, thinking_mode, context_resources)

    def interrupt_member_session(self, account_id: str, session_id: str, *, before: str | None = None) -> None:
        return self.lifecycle.interrupt_member_session(account_id, session_id, before=before)

    def cancel_turn(
        self,
        account_id: str,
        session_id: str,
        turn_id: str,
        preserve_partial: bool = True,
        *,
        reason: str = "cancelled",
    ) -> dict[str, Any]:
        return self.lifecycle.cancel_turn(account_id, session_id, turn_id, preserve_partial, reason=reason)

    def session_binding(self, account_id: str, session_id: str) -> dict[str, Any]:
        return self.queries.session_binding(account_id, session_id)

    def get_turn(
        self, account_id: str, session_id: str, turn_id: str
    ) -> dict[str, Any]:
        return self.queries.get_turn(account_id, session_id, turn_id)

    def list_conversations(
        self, account_id: str, *, cursor=None, limit=24
    ) -> dict[str, Any]:
        self.inputs.maintain_attachments(account_id)
        self.lifecycle.interrupt_expired_turn_jobs(account_id)
        result = self.queries.list_conversations(account_id, cursor=cursor, limit=limit)
        for session in result["sessions"]:
            if session["pending_turn_status"] == "queued" or (session["pending_turn_status"] is None and session["queued_input_count"]):
                self.lifecycle.resume_session_work(account_id, session["session_id"])
        return result

    def get_conversation(self, account_id: str, session_id: str) -> dict[str, Any]:
        self.inputs.maintain_attachments(account_id)
        self.lifecycle.interrupt_expired_turn_jobs(account_id)
        self.lifecycle.resume_session_work(account_id, session_id)
        return self.queries.get_conversation(account_id, session_id)

    def source_message_for_favorite(
        self, account_id: str, session_id: str, message_id: str
    ):
        return self.queries.source_message_for_favorite(account_id, session_id, message_id)

    def conversation_exists(self, account_id: str, session_id: str) -> bool:
        return self.queries.conversation_exists(account_id, session_id)

    def update_conversation(
        self,
        account_id: str,
        session_id: str,
        *,
        title: str | None = None,
        is_pinned: bool | None = None,
    ) -> dict[str, Any]:
        return self.sessions.update_conversation(account_id, session_id, title=title, is_pinned=is_pinned)

    def batch_pin_conversations(
        self,
        account_id: str,
        session_ids: list[str],
        is_pinned: bool,
    ) -> dict[str, Any]:
        return self.sessions.batch_pin_conversations(account_id, session_ids, is_pinned)

    def batch_delete_conversations(
        self,
        account_id: str,
        session_ids: list[str],
    ) -> dict[str, Any]:
        return self.sessions.batch_delete_conversations(account_id, session_ids)

    def fork_conversation(
        self,
        account_id: str,
        session_id: str,
        at_seq: Optional[int] = None,
    ) -> dict[str, Any]:
        return self.sessions.fork_conversation(account_id, session_id, at_seq)

    def delete_conversation(self, account_id: str, session_id: str) -> dict[str, Any]:
        return self.sessions.delete_conversation(account_id, session_id)
