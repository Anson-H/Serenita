import threading


from backend.app.core.cancellation import (
    CancellationToken,
    OperationCancelledError,
)


TURN_JOB_HEARTBEAT_SECONDS = 15


class ConversationTurnJobs:
    def __init__(
        self,
        repository,
        task_state,
        titles,
        *,
        execute_turn,
        record_failure,
        promote_next,
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
            try:
                turn = self.repository.turn_by_stream_id(
                    account_id, session_id, stream_id
                )
                claimed = bool(
                    turn is not None
                    and self.repository.claim_turn_job(
                        account_id, session_id, turn["turn_id"]
                    )
                )
            except Exception:
                claimed = False
                turn = None
            if not claimed or turn is None:
                try:
                    self.promote_next(account_id, session_id)
                except Exception:
                    # A deleted session or an unavailable persistence backend
                    # must not resurrect work from a removed queue.
                    pass
                finally:
                    with self.task_state.lock:
                        self.task_state.threads.pop(job_key, None)
                        if (
                            self.task_state.cancellations.get(job_key)
                            is cancellation_token
                        ):
                            self.task_state.cancellations.pop(job_key, None)
                return
            turn = self.repository.turn_by_stream_id(account_id, session_id, stream_id)
            if turn is None:
                with self.task_state.lock:
                    self.task_state.threads.pop(job_key, None)
                    if self.task_state.cancellations.get(job_key) is cancellation_token:
                        self.task_state.cancellations.pop(job_key, None)
                return
            stop_heartbeat = threading.Event()

            def heartbeat() -> None:
                while not stop_heartbeat.wait(TURN_JOB_HEARTBEAT_SECONDS):
                    self.repository.touch_turn_job(
                        account_id, session_id, turn["turn_id"]
                    )

            heartbeat_thread = threading.Thread(
                target=heartbeat,
                name=f"serenita-turn-heartbeat-{turn['turn_id']}",
                daemon=True,
            )
            heartbeat_thread.start()
            messages_by_id = self.repository.messages_by_id(
                account_id, turn["session_id"]
            )
            user_message = messages_by_id.get(turn["user_message_id"] or "") or {}
            title_thread = self.titles.start(account_id, turn, user_message)
            try:
                self.execute_turn(
                    account_id,
                    turn,
                    messages_by_id,
                    cancellation_token=cancellation_token,
                )
            except OperationCancelledError:
                # Cancellation owns the terminal record. It may arrive before
                # the producer enters its main try block; never overwrite it
                # with a failed turn while cancel_turn is still committing.
                pass
            except BaseException as exc:
                current = self.repository.turn_by_stream_id(
                    account_id, session_id, stream_id
                )
                if current is not None and current["status"] == "streaming":
                    self.record_failure(
                        account_id,
                        current,
                        "TURN_JOB_FAILED",
                        str(exc) or "Agent Turn 后台任务异常中断。",
                    )
            finally:
                stop_heartbeat.set()
                heartbeat_thread.join(timeout=1)
                if title_thread is not None:
                    title_thread.join(timeout=0.05)
                try:
                    self.promote_next(account_id, session_id)
                except Exception:
                    # Deletion wins over queue advancement; other failures are
                    # recovered from persisted state on the next session read.
                    pass
                finally:
                    # Queue authorization and advancement are part of the job;
                    # shutdown/test teardown must not outlive this disk access.
                    with self.task_state.lock:
                        self.task_state.threads.pop(job_key, None)
                        if (
                            self.task_state.cancellations.get(job_key)
                            is cancellation_token
                        ):
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
        thread.start()

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
