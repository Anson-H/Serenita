"""运行会话后台任务、维护执行心跳，并在任务结束后推进输入队列。"""

import logging
import threading
from typing import Any, Callable, Mapping, Protocol


from backend.app.core.cancellation import (
    CancellationToken,
    OperationCancelledError,
)


TURN_JOB_HEARTBEAT_SECONDS = 15


class ExecuteTurn(Protocol):
    def __call__(
        self,
        account_id: str,
        turn: Mapping[str, Any],
        messages_by_id: dict[str, dict[str, Any]],
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None: ...


class ConversationTurnJobs:
    def __init__(
        self,
        repository,
        task_state,
        titles,
        *,
        execute_turn: ExecuteTurn,
        record_failure: Callable[[str, Mapping[str, Any], str, str], None],
        promote_next: Callable[[str, str], dict[str, Any] | None],
    ):
        self.repository = repository
        self.task_state = task_state
        self.titles = titles
        self.execute_turn = execute_turn
        self.record_failure = record_failure
        self.promote_next = promote_next

    def start(self, account_id: str, session_id: str, stream_id: str) -> None:
        """Start an Agent Turn independently of any SSE subscriber."""

        job_key = (account_id, session_id, stream_id)
        cancellation_token = CancellationToken()

        def run() -> None:
            turn = None
            heartbeat_thread = None
            title_thread = None
            stop_heartbeat = threading.Event()
            try:
                turn = self.repository.turn_by_stream_id(account_id, session_id, stream_id)
                if turn is None or not self.repository.claim_turn_job(
                    account_id, session_id, turn["turn_id"]
                ):
                    return
                turn = self.repository.turn_by_stream_id(account_id, session_id, stream_id)
                if turn is None:
                    return

                def heartbeat() -> None:
                    while not stop_heartbeat.wait(TURN_JOB_HEARTBEAT_SECONDS):
                        try:
                            self.repository.touch_turn_job(account_id, session_id, turn["turn_id"])
                        except Exception:
                            logging.getLogger(__name__).exception("Current turn heartbeat failed")
                            return

                heartbeat_thread = threading.Thread(
                    target=heartbeat,
                    name=f"serenita-turn-heartbeat-{turn['turn_id']}",
                    daemon=True,
                )
                heartbeat_thread.start()
                messages_by_id = self.repository.messages_by_id(account_id, turn["session_id"])
                user_message = messages_by_id.get(turn["user_message_id"] or "") or {}
                title_thread = self.titles.start(account_id, turn, user_message)
                self.execute_turn(
                    account_id, turn, messages_by_id,
                    cancellation_token=cancellation_token,
                )
            except OperationCancelledError:
                # The cancellation command owns its terminal record.
                pass
            except BaseException as exc:
                try:
                    current = self.repository.turn_by_stream_id(account_id, session_id, stream_id)
                    if current is not None and current["status"] == "streaming":
                        self.record_failure(
                            account_id, current, "TURN_JOB_FAILED",
                            str(exc) or "当前轮次后台任务异常中断。",
                        )
                except Exception:
                    logging.getLogger(__name__).exception("Failed to record current turn failure")
            finally:
                stop_heartbeat.set()
                if heartbeat_thread is not None and heartbeat_thread.ident is not None:
                    heartbeat_thread.join(timeout=1)
                if title_thread is not None:
                    title_thread.join(timeout=0.05)
                try:
                    self.promote_next(account_id, session_id)
                except Exception:
                    # Persisted queue state is retried on the next session read.
                    logging.getLogger(__name__).exception("Failed to advance current turn queue")
                finally:
                    with self.task_state.lock:
                        self.task_state.threads.pop(job_key, None)
                        if self.task_state.cancellations.get(job_key) is cancellation_token:
                            self.task_state.cancellations.pop(job_key, None)

        thread = threading.Thread(
            target=run,
            name=f"serenita-agent-turn-{stream_id}",
            daemon=True,
        )
        with self.task_state.lock:
            existing = self.task_state.threads.get(job_key)
            if existing is not None and existing.is_alive():
                return
            self.task_state.threads[job_key] = thread
            self.task_state.cancellations[job_key] = cancellation_token
        try:
            thread.start()
        except BaseException:
            with self.task_state.lock:
                if self.task_state.threads.get(job_key) is thread:
                    self.task_state.threads.pop(job_key, None)
                if self.task_state.cancellations.get(job_key) is cancellation_token:
                    self.task_state.cancellations.pop(job_key, None)
            raise

    def wait(
        self,
        account_id: str,
        session_id: str,
        stream_id: str,
        timeout: float = 2.0,
    ) -> None:
        with self.task_state.lock:
            thread = self.task_state.threads.get((account_id, session_id, stream_id))
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout)

    def cancel(
        self,
        account_id: str,
        session_id: str,
        stream_id: str,
    ) -> None:
        with self.task_state.lock:
            cancellation_token = self.task_state.cancellations.get(
                (account_id, session_id, stream_id)
            )
        if cancellation_token is not None:
            cancellation_token.cancel()
