"""Register and inspect authorized vector-delivery tasks and their source scope."""
from __future__ import annotations

from collections import defaultdict
import json

from backend.app.core.values import digest as fingerprint
from backend.app.domain.memory.vectors import fail
from backend.app.schemas.memory.append import stable_memory_id


class MemoryIndexRegistry:
    """Persist and read current vector-delivery registrations under binding ownership."""
    def __init__(self, repository, *, check_running):
        self.repository, self.memory = repository, repository.memory
        self.check_running = check_running

    def attempt_payload(self, actor, member, operation, pending, cutoff, event_id, previous_attempt=None):
        attempt = stable_memory_id(member, operation, "processing_attempt", pending["status_id"])
        return {"attempts": [{"attempt_id": attempt, "previous_attempt_id": previous_attempt, "task_kind": "vector_index",
                "purpose": "为已保存事件的检索文本生成并保存固定空间向量。", "input_sequence": cutoff, "coverage": self.source_coverage(actor, member, event_id), "input_references": [{"object_type": "vector_status", "object_id": pending["binding_id"], "item_id": pending["status_id"]}]}],
            "attempt_updates": [{"attempt_id": attempt, "processing_status": "pending"}]}

    def source_coverage(self, actor, member, event_id):
        repo = self.memory
        with repo._transaction(actor, member) as (access, connection):
            description = repo._require(connection, access, "event", event_id)
            from backend.app.repositories.memory.sources.evidence import change_references,read_change
            changes=defaultdict(list)
            for ref in change_references(repo,connection,access,description):
                change=read_change(repo,access,ref,connection)
                changes[(change['source_category'],change['source_database'])].append(ref)
        return [{'source_category':category,'source_database':database,
            'business_changes':changes[(category,database)]} for category,database in sorted(changes)]

    def require_formation_scope(self, actor, member, event_id):
        repo = self.memory
        with repo._transaction(actor, member) as (access, connection):
            setting = repo._settings(connection, access)
            if setting["formation_state"] != "enabled":
                fail("MEMORY_FORMATION_NOT_ENABLED", "当前设置不允许此次向量形成。", kind="forbidden")
            description = repo._require(connection, access, "event", event_id)
            from backend.app.repositories.memory.sources.evidence import evidence_categories
            if not evidence_categories(repo,connection,access,description)<=set(setting['source_categories']):
                fail('MEMORY_SOURCE_SCOPE_DISABLED','当前来源类别未获准形成记忆索引。',kind='forbidden')

    def configuration_attempt(self, actor, member, operation):
        identity = stable_memory_id(member, operation, "processing_attempt", "configuration")
        with self.memory._transaction(actor, member) as (access, connection):
            return identity if self.memory._record(connection, access, "processing_attempt", identity) else None

    def record_configuration_failure(self, actor, member, operation, description, model_id, dimensions, error):
        self.require_formation_scope(actor, member, description)
        repo = self.memory
        attempt = stable_memory_id(member, operation, "processing_attempt", "configuration")
        references = [{"object_type": "event", "object_id": description}]
        with self.repository.vectors.binding_guard(self.repository.require(actor, member, "event", description)["account_id"], attempt, check_running=self.check_running):
            with repo._transaction(actor, member) as (access, connection):
                existing = repo._record(connection, access, "processing_attempt", attempt)
                status = existing if existing and existing["processing_status"] == "failed" else None
                previous = existing["updated_commit_id"] if existing else stable_memory_id(member, operation + ":configuration-pending", "commit", "commit")
                parameters = connection.execute("SELECT * FROM vector_requests WHERE attempt_id=?", (attempt,)).fetchone() if connection else None
                if parameters and (parameters["event_id"], parameters["requested_model_id"], parameters["requested_dimensions"]) != (description, model_id, dimensions):
                    fail("MEMORY_INDEX_OPERATION_CONFLICT", "同一索引操作的原始请求参数不同。", kind="conflict")
            if status:
                return {"event_id": description, "attempt_id": attempt, "status": {"state": "failed", "error_code": status["error_code"], "error_message": status["error_message"]}, "replayed": True}
            if existing is None:
                cutoff = repo.snapshot(actor, member)["record_cutoff"]
                repo.write(actor, member, operation + ":configuration-pending", {
                    "attempts": [{"attempt_id": attempt, "task_kind": "vector_index", "purpose": "为明确请求的事件等待可用向量配置。", "input_sequence": cutoff, "coverage": self.source_coverage(actor, member, description), "input_references": references}],
                    "vector_request_parameters": [{"attempt_id": attempt, "event_id": description, "operation_id": operation,
                        "requested_model_id": model_id, "requested_dimensions": dimensions}],
                    "attempt_updates": [{"attempt_id": attempt, "processing_status": "pending"}]},
                    command={"event_id": description, "model_id": model_id, "dimensions": dimensions})
            repo.write(actor, member, operation + ":configuration-failed", {
                "attempt_updates": [{"attempt_id": attempt, 'expected_updated_commit_id': previous, "processing_status": "failed", "error_code": error.code, "error_message": error.message, "result_references": references}]})
        return {"event_id": description, "attempt_id": attempt, "status": {"state": "failed", "error_code": error.code, "error_message": error.message}, "replayed": False}

    def request_retry(self, actor, member, failed_attempt_id, operation_id):
        """Register an explicit retry from immutable parameters without a model call."""
        from backend.app.schemas.memory.append import canonical_uuid
        canonical_uuid(failed_attempt_id)
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 200:
            fail("MEMORY_INVALID_OPERATION", "重试操作标识必须为非空且不超过 200 字符的字符串。")
        self.check_running()
        repo = self.memory
        command = {"action": "retry_vector_index", "previous_attempt_id": failed_attempt_id}
        request_hash = fingerprint({"actor_account_id": actor, "member_id": member,
            "request": command})

        def replay():
            with repo._transaction(actor, member, write=True) as (access, db):
                commit = db.execute("SELECT * FROM commits WHERE account_id=? AND member_id=? AND operation_id=?", (access.account_id, member, operation_id)).fetchone()
                if commit is None:
                    return None
                if commit["request_hash"] != request_hash:
                    fail("MEMORY_OPERATION_CONFLICT", "相同重试操作标识的目标与原请求不一致。", kind="conflict")
                result = repo._commit_result(db, commit, replayed=True, access=access)
                references = result["objects"].get("processing_attempt", [])
                if len(references) != 1:
                    fail("MEMORY_INDEX_RETRY_RECEIPT", "重试回执缺少唯一计算尝试。")
                attempt = repo._require(db, access, "processing_attempt", references[0]["object_id"])
                return repo._project(db, access, attempt, repo._cutoff(db, access))

        repeated = replay()
        if repeated is not None:
            return repeated
        with repo._transaction(actor, member, write=True) as (access, db):
            previous = repo._require(db, access, "processing_attempt", failed_attempt_id)
            if previous["task_kind"] != "vector_index":
                fail("MEMORY_RETRY_KIND", "此能力仅重试已登记的向量索引计算。")
            parameters = db.execute("SELECT * FROM vector_requests WHERE attempt_id=?", (failed_attempt_id,)).fetchone()
            if parameters is not None:
                parameters = dict(parameters)
                binding_id = None
                event_id = parameters["event_id"]
                original_operation = None
            else:
                # Terminal result references may be empty. The first processing
                # status retains the exact pending vector status identity.
                initial = db.execute("SELECT input_references_json FROM processing_attempts WHERE attempt_id=?", (failed_attempt_id,)).fetchone()
                references = json.loads(initial[0]) if initial else []
                refs = [row for row in references if row["object_type"] == "vector_status"]
                if len(refs) != 1:
                    fail("MEMORY_INDEX_RETRY_PARAMETERS", "计算尝试缺少实际索引请求参数。")
                pending_reference = refs[0]
                binding_id = pending_reference["object_id"]
                binding = repo._require(db, access, "vector_binding", binding_id)
                event_id = binding["event_id"]
                commit = db.execute("SELECT operation_id FROM commits WHERE commit_id=?", (binding["commit_id"],)).fetchone()
                original_operation = commit[0][:-8] if commit and commit[0].endswith(":binding") else None
                if original_operation is None or stable_memory_id(member, original_operation, "processing_attempt", pending_reference["item_id"]) != failed_attempt_id:
                    fail("MEMORY_INDEX_RETRY_PARAMETERS", "计算尝试与实际绑定身份不一致。")
            account = access.account_id
        self.require_formation_scope(actor, member, event_id)
        with self.repository.vectors.binding_guard(account, binding_id or failed_attempt_id, check_running=self.check_running):
            repeated = replay()
            if repeated is not None:
                return repeated
            with repo._transaction(actor, member, write=True) as (access, db):
                previous = repo._project(db, access, repo._require(db, access, "processing_attempt", failed_attempt_id), repo._cutoff(db, access))
                if previous["processing_status"] not in {"failed", "cancelled"}:
                    fail("MEMORY_RETRY_STATE", "只有已失败或已取消的向量计算可以重试。")
                if db.execute("SELECT 1 FROM processing_attempts WHERE previous_attempt_id=? LIMIT 1", (failed_attempt_id,)).fetchone():
                    fail("MEMORY_INDEX_RETRY_SUPERSEDED", "该计算已有后续尝试，请读取当前处理状态。", kind="conflict")
                cutoff = repo._cutoff(db, access)
                head = repo._project(db, access, repo._require(db, access, "vector_binding", binding_id), cutoff)["status"] if binding_id else None
            if binding_id is None:
                identity = stable_memory_id(member, operation_id, "processing_attempt", "configuration")
                payload = {
                    "attempts": [{"attempt_id": identity, "previous_attempt_id": failed_attempt_id, "task_kind": "vector_index",
                        "purpose": previous["purpose"], "input_sequence": cutoff, "coverage": self.source_coverage(actor, member, event_id), "input_references": previous["input_references"]}],
                    "vector_request_parameters": [{"attempt_id": identity, "event_id": event_id, "operation_id": operation_id,
                        "requested_model_id": parameters["requested_model_id"], "requested_dimensions": parameters["requested_dimensions"]}],
                    "attempt_updates": [{"attempt_id": identity, "processing_status": "pending"}]}
            else:
                # A stopped execution may have prevented its final vector
                # failure. Preserve that gap and the new pending state with
                # the retry attempt in one SQLite transaction.
                statuses = []
                old_pending_id = head["status_id"] if head["state"] == "pending" else head.get("previous_status_id")
                if head["state"] == "confirmed" or old_pending_id != pending_reference["item_id"]:
                    fail("MEMORY_INDEX_RETRY_SUPERSEDED", "该绑定已有后续交付，请读取当前处理状态。", kind="conflict")
                if head["state"] == "pending":
                    head = {"binding_id": binding_id, "status_id": stable_memory_id(member, operation_id, "vector_status", "stopped"),
                        "previous_status_id": head["status_id"], "state": "failed", "error_code": "MEMORY_VECTOR_ATTEMPT_STOPPED",
                        "error_message": "前次计算尝试已停止，新交付作为独立重试保留。"}
                    statuses.append(head)
                pending = {"binding_id": binding_id, "status_id": stable_memory_id(member, operation_id, "vector_status", "pending"),
                    "previous_status_id": head["status_id"], "state": "pending"}
                statuses.append(pending)
                payload = {"vector_statuses": statuses,
                    **self.attempt_payload(actor, member, original_operation, pending, cutoff, event_id, failed_attempt_id)}
                identity = payload["attempts"][0]["attempt_id"]
            repo.write(actor, member, operation_id, payload, command=command)
            return repo.read(actor, member, [{"object_type": "processing_attempt", "object_id": identity}])["objects"][0]

    def pending_recoveries(self, actor, member, limit=20):
        """List only registered pending deliveries; failures require explicit retry."""
        if type(limit) is not int or not 1 <= limit <= 100:
            fail("MEMORY_RECOVERY_LIMIT", "单次向量恢复数量必须为 1 至 100。")
        self.check_running()
        setting = self.memory.settings(actor, member)
        if not setting or setting["formation_state"] != "enabled":
            return []
        commands = []
        repo = self.memory
        from backend.app.repositories.memory.processing.formation_queue import execution_active
        with repo._transaction(actor, member) as (access, connection):
            if connection is None:
                return []
            rows = connection.execute(
                "SELECT b.binding_id,b.event_id,b.space_id,c.operation_id,s.status_id "
                "FROM event_vectors b JOIN commits c ON c.commit_id=b.commit_id "
                "JOIN event_vector_statuses s ON s.binding_id=b.binding_id "
                "WHERE b.account_id=? AND b.member_id=? AND s.state='pending' "
                "AND NOT EXISTS(SELECT 1 FROM event_vector_statuses n "
                "WHERE n.binding_id=s.binding_id AND n.previous_status_id=s.status_id) "
                "ORDER BY c.sequence", (access.account_id, member)).fetchall()
            for row in rows:
                if not row['operation_id'].endswith(':binding'):
                    continue
                operation = row['operation_id'][:-8]
                attempt_id = stable_memory_id(member, operation, 'processing_attempt', row['status_id'])
                task = repo._record(connection, access, 'processing_attempt', attempt_id)
                if not repo._visible(connection, access, task) or task['processing_status'] not in {'pending', 'running'}:
                    continue
                if execution_active(repo, actor, member, attempt_id):
                    continue
                binding = repo._record(connection, access, 'vector_binding', row['binding_id'])
                if not repo._visible(connection, access, binding):
                    continue
                space = repo._require(connection, access, 'vector_space', row['space_id'])
                commands.append({'operation_id': operation, 'event_id': row['event_id'],
                    'model_id': space['model_id'], 'model_account_id': access.account_id,
                    'dimensions': space['dimensions'], 'space_id': row['space_id'],
                    'binding_id': row['binding_id'], 'status_id': row['status_id'],
                    'attempt_id': attempt_id, 'processing_status': task['processing_status']})
                if len(commands) == limit:
                    return commands
            rows = connection.execute(
                "SELECT r.* FROM vector_requests r JOIN commits c ON c.commit_id=r.commit_id "
                "JOIN processing_attempts p ON p.attempt_id=r.attempt_id "
                "WHERE r.account_id=? AND r.member_id=? AND p.processing_status IN ('pending','running') "
                "ORDER BY c.sequence", (access.account_id, member)).fetchall()
            for row in rows:
                identity = stable_memory_id(member, row['operation_id'], 'vector_binding', row['event_id'])
                if connection.execute('SELECT 1 FROM event_vectors WHERE binding_id=?', (identity,)).fetchone():
                    continue
                task = repo._record(connection, access, 'processing_attempt', row['attempt_id'])
                if not repo._visible(connection, access, task) or execution_active(repo, actor, member, row['attempt_id']):
                    continue
                commands.append({'operation_id': row['operation_id'], 'event_id': row['event_id'],
                    'model_id': row['requested_model_id'],
                    'requested_model_id': row['requested_model_id'], 'model_account_id': access.account_id,
                    'dimensions': row['requested_dimensions'], 'binding_id': None,
                    'attempt_id': row['attempt_id'], 'processing_status': task['processing_status']})
                if len(commands) == limit:
                    break
        return commands

