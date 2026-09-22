"""Deliver and recover append-only vector bindings with explicit storage confirmation."""
from __future__ import annotations
from backend.app.domain.memory.event_text import event_text


from backend.app.core.errors import SerenitaError
from backend.app.core.cancellation import OperationCancelledError
from backend.app.repositories.memory.indexing.index_repository import MemoryIndexRepository
from backend.app.domain.memory.vectors import fail
from backend.app.schemas.memory.append import stable_memory_id






from backend.app.application.memory.vector_models import MemoryVectorModels


class MemoryIndexService:
    def __init__(self, memory_service, *, repository=None, vector_models=None,
                 embedding=None, cancellation_token=None, deadline=None, retry_failed=False):
        self.memory = memory_service
        self.repository = repository or MemoryIndexRepository(memory_service.repository)
        self.vector_models = vector_models or MemoryVectorModels(memory_service, embedding=embedding,
            cancellation_token=cancellation_token, deadline=deadline)
        self.retry_failed = retry_failed
        from backend.app.repositories.memory.indexing.index_registry import MemoryIndexRegistry
        self.registry = MemoryIndexRegistry(self.repository, check_running=self.vector_models.check_running)

    def index_event(self, actor, member, operation_id, event_id, *, model_id=None, dimensions=None, pending_only=False):
        """Save a vector and confirm the successful storage result.

        Retrying the same operation resumes its binding. A failed binding gets
        a new pending status; confirmed is terminal. Each attempt is preserved.
        """
        self.vector_models.check_running()
        repo = self.repository
        with self.memory.repository.members.access_guard(actor, member, write=True):
            description = repo.require(actor, member, "event", event_id)
        account = description["account_id"]
        model_id = model_id or self.vector_models.default_model_id(account)
        try:
            if model_id is None:
                fail("MEMORY_EMBEDDING_MODEL_REQUIRED", "请在默认模型中设置文本向量模型。")
            space = self.vector_models.space(account, member, model_id, dimensions)
        except SerenitaError as exc:
            return self.registry.record_configuration_failure(actor, member, operation_id, event_id, model_id, dimensions, exc)
        binding_id = stable_memory_id(member, operation_id, "vector_binding", event_id)
        with repo.vectors.binding_guard(account, binding_id, check_running=self.vector_models.check_running):
            snapshot = repo.binding_snapshot(actor, member, binding_id, space["space_id"])
            binding = snapshot["binding"]
            fresh = binding is None
            attempt = None
            if binding is not None:
                if binding["event_id"] != event_id or binding["space_id"] != space["space_id"]:
                    fail("MEMORY_INDEX_OPERATION_CONFLICT", "同一索引操作的描述或空间参数不同。", kind="conflict")
                status = binding["status"]
                if status["state"] == "pending":
                    attempt_id = stable_memory_id(member, operation_id, "processing_attempt", status["status_id"])
                    attempt = self.memory.repository.read(actor, member, [{"object_type": "processing_attempt", "object_id": attempt_id}])["objects"][0]
                    if attempt["processing_status"] in {"cancelled", "failed"}:
                        if pending_only or not self.retry_failed:
                            return {"binding_id": binding_id, "status": status, "skipped": "explicit_retry_required"}
                        status = self._append_status(actor, member, operation_id, binding_id, status, "failed", error_code="MEMORY_VECTOR_ATTEMPT_STOPPED", error_message="前次计算尝试已停止，新交付必须保留独立重试。")
                if status["state"] == "confirmed":
                    return {"binding_id": binding_id, "space_id": space["space_id"], "space": space, "status": status, "replayed": True}
                if status["state"] == "failed":
                    if pending_only or not self.retry_failed:
                        return {"binding_id": binding_id, "space_id": space["space_id"], "space": space, "status": status, "skipped": "explicit_retry_required"}
                    status = self._append_status(actor, member, operation_id, binding_id, status, "pending")
                    attempt = None
            else:
                binding = {"binding_id": binding_id, "event_id": event_id, "space_id": space["space_id"],
                           "vector_id": stable_memory_id(member, operation_id, "vector", event_id), "text_hash": description["text_hash"]}
                status = {"binding_id": binding_id, "status_id": stable_memory_id(member, operation_id, "vector_status", "initial"), "state": "pending"}
                payload = {"vector_bindings": [{key: value for key, value in binding.items() if key != "text_hash"}], "vector_statuses": [status],
                    **self.registry.attempt_payload(actor, member, operation_id, status, snapshot["record_cutoff"], event_id,
                        self.registry.configuration_attempt(actor, member, operation_id))}
                if snapshot["space"] is None:
                    payload["vector_spaces"] = [space]
                commit = self.memory.repository.write(actor, member, operation_id + ":binding", payload)
                attempt = {**payload["attempts"][0], **payload["attempt_updates"][0],
                    "updated_commit_id": commit["commit_id"]}
            try:
                # Recheck live evidence immediately before sending text outside
                # the application and before each physical/metadata commit.
                self.registry.require_formation_scope(actor, member, event_id)
                repo.require(actor, member, "event", event_id)
                attempt = self._mark_delivery_running(actor, member, operation_id, status, attempt=attempt)
                existing = [] if fresh else repo.vectors.rows(account, space, binding["vector_id"])
                if existing:
                    digest = existing[0]["vector_hash"]
                    repo.vectors.verify(account, member, binding, space, digest)
                else:
                    vector = self.vector_models.embed(account, member, space, event_text(description))
                    self.registry.require_formation_scope(actor, member, event_id)
                    repo.require(actor, member, "event", event_id)
                    digest = repo.vectors.add(account, member, binding, space, vector)
                self.vector_models.check_running()
                confirmed = self._append_status(actor, member, operation_id, binding_id, status, "confirmed", attempt=attempt, vector_hash=digest)
                return {"binding_id": binding_id, "space_id": space["space_id"], "space": space, "status": confirmed, "replayed": False}
            except Exception as exc:
                code = exc.code if isinstance(exc, SerenitaError) else ("MEMORY_VECTOR_CANCELLED" if isinstance(exc, OperationCancelledError) else "MEMORY_VECTOR_WRITE_FAILED")
                message = exc.message if isinstance(exc, SerenitaError) else ("向量交付已取消。" if isinstance(exc, OperationCancelledError) else "向量生成、追加或确认失败。")
                try:
                    failed = self._append_status(actor, member, operation_id, binding_id, status, "failed", attempt=attempt, error_code=code, error_message=message)
                except SerenitaError:
                    # Access may have been revoked after embedding; even a
                    # failure record cannot bypass the live evidence boundary.
                    raise exc
                if isinstance(exc, OperationCancelledError):
                    raise
                return {"binding_id": binding_id, "space_id": space["space_id"], "space": space, "status": failed, "replayed": False}

    def _mark_delivery_running(self, actor, member, operation, pending, *, attempt=None):
        attempt_id = stable_memory_id(member, operation, "processing_attempt", pending["status_id"])
        if attempt is None:
            attempt = self.memory.repository.read(actor, member,
                [{"object_type": "processing_attempt", "object_id": attempt_id}])["objects"][0]
        if attempt["processing_status"] == "pending":
            commit = self.memory.repository.write(actor, member, operation + ":running:" + pending["status_id"], {
                "attempt_updates": [{"attempt_id": attempt_id, 'expected_updated_commit_id': attempt['updated_commit_id'], "processing_status": "running"}]})
            attempt = {**attempt, "processing_status": "running", "updated_commit_id": commit["commit_id"]}
        return attempt

    def _append_status(self, actor, member, operation, binding, previous, state, *, attempt=None, **fields):
        label = previous["status_id"] + ":" + state
        status = {"binding_id": binding, "status_id": stable_memory_id(member, operation, "vector_status", label),
                  "previous_status_id": previous["status_id"], "state": state, **fields}
        batch = {"vector_statuses": [status]}
        if state == "pending":
            old_pending = previous.get("previous_status_id")
            previous_attempt = stable_memory_id(member, operation, "processing_attempt", old_pending) if old_pending else None
            batch.update(self.registry.attempt_payload(actor, member, operation, status, self.memory.repository.snapshot(actor, member)["record_cutoff"], self.repository.require(actor, member, "vector_binding", binding)["event_id"], previous_attempt))
        else:
            attempt_id = stable_memory_id(member, operation, "processing_attempt", previous["status_id"])
            actual = attempt if attempt is not None else self.memory.repository.read(actor, member,
                [{"object_type": "processing_attempt", "object_id": attempt_id}])["objects"][0]
            batch["attempt_updates"] = [{"attempt_id": attempt_id, 'expected_updated_commit_id': actual['updated_commit_id'], "processing_status": "completed" if state == "confirmed" else "failed", "result_references": [{"object_type": "vector_status", "object_id": binding, "item_id": status["status_id"]}], **({"error_code": fields["error_code"], "error_message": fields["error_message"]} if state == "failed" else {})}]
            if actual["processing_status"] in {"failed", "cancelled"} and state == "failed":
                batch["attempt_updates"] = []
        self.memory.repository.write(actor, member, operation + ":status:" + status["status_id"], batch)
        return status


    def prepare_recovery(self, actor, member, job):
        """Start queued delivery; terminate an interrupted delivery without retry."""
        self.vector_models.check_running()
        self.registry.require_formation_scope(actor, member, job["event_id"])
        if job["binding_id"] is None:
            if job['processing_status'] != 'running':
                return job
            from backend.app.repositories.memory.processing.formation_queue import execution_guard
            from backend.app.application.memory.processing.tasks import MemoryProcessingService
            with execution_guard(self.memory.repository, actor, member, job['attempt_id']) as acquired:
                if not acquired:
                    return None
                processing = MemoryProcessingService(self.memory)
                task = processing.read(actor, member, job['attempt_id'])
                if task['processing_status'] == 'running':
                    processing.finish(actor, member, task, 'failed',
                        error_code='MEMORY_EXECUTION_INTERRUPTED', error_message='前次执行已中断。')
                return None
        account = self.repository.require(actor, member, "vector_binding", job["binding_id"])["account_id"]
        with self.repository.vectors.binding_guard(account, job["binding_id"], check_running=self.vector_models.check_running):
            binding = self.memory.repository.read(actor, member, [{"object_type": "vector_binding", "object_id": job["binding_id"]}])["objects"][0]
            head = binding["status"]
            if head is None or head["state"] != "pending" or head["status_id"] != job["status_id"]:
                return None
            from backend.app.repositories.memory.processing.formation_queue import execution_guard
            with execution_guard(self.memory.repository, actor, member, job["attempt_id"]) as acquired:
                if not acquired:
                    return None
                attempt = self.memory.repository.read(actor, member,
                    [{"object_type": "processing_attempt", "object_id": job["attempt_id"]}])["objects"][0]
                if attempt["processing_status"] == "pending":
                    return job
                self._append_status(actor, member, job["operation_id"], job["binding_id"], head, "failed", error_code="MEMORY_VECTOR_DELIVERY_INTERRUPTED", error_message="前次向量交付已中断。")
                return None

    def resume_pending(self, actor, member, job):
        """Resume one host-selected current delivery under the caller's budget."""
        self.vector_models.check_running()
        self.registry.require_formation_scope(actor, member, job["event_id"])
        if job["binding_id"] is not None:
            binding = self.memory.repository.read(actor, member, [{"object_type": "vector_binding", "object_id": job["binding_id"]}])["objects"][0]
            status = binding["status"]
            if status["state"] != "pending" or status["status_id"] != job["status_id"]:
                return {"binding_id": job["binding_id"], "status": status, "skipped": "pending_changed"}
            try:
                actual_space = self.vector_models.space(binding["account_id"], member, job["model_id"], job["dimensions"])
                if actual_space["space_id"] != binding["space_id"]:
                    fail("MEMORY_VECTOR_SPACE_CHANGED", "当前配置与已登记向量空间不同，自动恢复已经停止。")
            except SerenitaError as exc:
                failed = self._append_status(actor, member, job["operation_id"], job["binding_id"], status, "failed",
                    error_code=exc.code, error_message=exc.message)
                return {"binding_id": job["binding_id"], "status": failed, "replayed": False}
        else:
            task = self.memory.repository.read(actor, member, [{"object_type": "processing_attempt", "object_id": job["attempt_id"]}])["objects"][0]
            if task["processing_status"] not in {"pending", "running"}:
                return {"attempt_id": job["attempt_id"], "skipped": "pending_changed"}
            if task['processing_status'] == 'pending':
                self.memory.repository.write(actor, member, job['operation_id'] + ':configuration-running', {
                    'attempt_updates':[{'attempt_id':task['attempt_id'], 'expected_updated_commit_id':task['updated_commit_id'], 'processing_status':'running'}]})
            # The scheduler chooses an execution envelope from this captured
            # actual model. Never resolve a new default outside that envelope.
            try:
                if job["model_id"] is None:
                    fail("MEMORY_EMBEDDING_MODEL_REQUIRED", "本次登记的恢复范围尚无可用向量模型。")
                self.vector_models.space(job["model_account_id"], member, job["model_id"], job["dimensions"])
            except SerenitaError as exc:
                return self.registry.record_configuration_failure(actor, member, job["operation_id"], job["event_id"],
                    job["requested_model_id"], job["dimensions"], exc)
        result = self.index_event(actor, member, job["operation_id"], job["event_id"],
            model_id=job["model_id"], dimensions=job["dimensions"], pending_only=True)
        if job["binding_id"] is None and result.get("binding_id"):
            task = self.memory.repository.read(actor, member, [{"object_type": "processing_attempt", "object_id": job["attempt_id"]}])["objects"][0]
            if task["processing_status"] in {"pending", "running"}:
                self.memory.repository.write(actor, member, job["operation_id"] + ":configuration-resolved", {
                    "attempt_updates": [{"attempt_id": job["attempt_id"], 'expected_updated_commit_id': task['updated_commit_id'], "processing_status": "completed", "result_references": [{"object_type": "vector_binding", "object_id": result["binding_id"]}]}]})
        return result


    def request_retry(self, actor, member, failed_attempt_id, operation_id):
        """Register a user-requested retry without performing model work."""
        return self.registry.request_retry(actor, member, failed_attempt_id, operation_id)

    def pending_recoveries(self, actor, member, limit=20):
        jobs = self.registry.pending_recoveries(actor, member, limit)
        for job in jobs:
            if job['model_id'] is None:
                job['model_id'] = self.vector_models.default_model_id(job['model_account_id'])
        return jobs
