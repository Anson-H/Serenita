"""Append-only memory transactions with member and source access checks."""
from __future__ import annotations
from backend.app.core.time import local_now
from backend.app.schemas.memory.values import occurrence_time_bounds

from contextlib import contextmanager
import hashlib
import json
import sqlite3
from typing import Callable

from backend.app.core.errors import SerenitaError
from backend.app.domain.memory.sources import default_memory_settings
from backend.app.core.pagination import seek_cursor, seek_position
from backend.app.repositories.members.repository import MemberRepository
from backend.app.repositories.memory.reading.read_cache import (
    MAX_ROWS, current_read_cache, immutable_read_scope,
)
from backend.app.repositories.memory.transaction import memory_database_guard
from backend.app.schemas.memory.append import MemoryWrite, MemoryQuery, MemoryReference, canonical_uuid, memory_time_bounds, stable_memory_id
from backend.app.storage.memory.database import MEMORY_COLLECTIONS, MEMORY_DATABASE_SCHEMA, MEMORY_OBJECTS
from backend.app.storage.paths import app_paths
from backend.app.storage.sqlite import connect


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


from backend.app.core.values import strict_digest as _digest


def _error(kind, code, message):
    raise SerenitaError(kind, code, message)


from backend.app.domain.memory.references import DETAIL_REFERENCES, VERSION_REFERENCES
EPISODE_KINDS = {"episode", "episode_revision", "episode_membership"}



def _now():
    return local_now().isoformat(timespec="microseconds")




class MemoryRepository:
    def __init__(self, paths=None, member_repository=None, *, source_access_check: Callable | None = None):
        self.paths = paths or app_paths()
        self.members = member_repository or MemberRepository(paths=self.paths)
        # The application resolves original resource existence and source access.
        # Persisted restrictions remain independently enforced here.
        self.source_access_check = source_access_check
        from backend.app.repositories.memory.reading.evidence_repository import MemoryEvidenceRepository
        self.evidence = MemoryEvidenceRepository(self)
        from backend.app.repositories.memory.processing.processing_repository import MemoryProcessingRepository
        self.processing = MemoryProcessingRepository(self)

    def path_for_account(self, account_id):
        return self.paths.memory_db(account_id)

    @contextmanager
    def _transaction(self, actor_account_id, member_id, *, write=False):
        canonical_uuid(actor_account_id)
        canonical_uuid(member_id)
        with self.members.access_guard(actor_account_id, member_id, write=write) as access:
            from backend.app.repositories.memory.processing.staging_scope import staging
            draft = staging(self, actor_account_id, member_id)
            if draft is not None:
                with draft.transaction(access, write=write) as connection:
                    yield access, connection
                return
            path = self.path_for_account(access.account_id)
            with memory_database_guard(path, write=write):
                with self._database_transaction(path, access, write=write) as connection:
                    yield access, connection

    @contextmanager
    def _database_transaction(self, path, access, *, write):
        from backend.app.storage.database_lifecycle import validate_database
        exists = validate_database(MEMORY_DATABASE_SCHEMA, path)
        if not exists and not write:
            yield None
            return
        with connect(path) as connection:
            connection.execute("PRAGMA recursive_triggers = ON")
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            if not exists:
                MEMORY_DATABASE_SCHEMA.create(connection)
            from backend.app.repositories.memory.transaction import memory_transaction_scope
            with memory_transaction_scope(connection, access), immutable_read_scope(connection, access, write=write) as cache:
                yield connection
                if cache is not None:
                    self._recheck_read_sources(connection, access, cache)

    @staticmethod
    def _cutoff(connection, access, requested=None):
        maximum = 0 if connection is None else connection.execute(
            "SELECT COALESCE(max(sequence),0) FROM commits WHERE account_id=? AND member_id=?",
            (access.account_id, access.member_id),
        ).fetchone()[0]
        if requested is not None and (not isinstance(requested, int) or isinstance(requested, bool) or requested < 0 or requested > maximum):
            _error("invalid_input", "MEMORY_INVALID_CUTOFF", "记录截点不在当前可读提交范围内。")
        return maximum if requested is None else requested

    def snapshot(self, actor_account_id, member_id, record_cutoff=None):
        with self._transaction(actor_account_id, member_id) as (access, connection):
            cutoff = self._cutoff(connection, access, record_cutoff)
            return {"member_id": member_id, "record_cutoff": cutoff}

    def _settings(self, connection, access):
        if connection is None:
            row = None
        else:
            row = connection.execute(
                "SELECT s.*, c.submitted_at FROM settings_history s JOIN commits c USING(commit_id) "
                "WHERE s.account_id=? AND s.member_id=? ORDER BY c.sequence DESC LIMIT 1",
                (access.account_id, access.member_id),
            ).fetchone()
        if row is None:
            return default_memory_settings(access)
        result = self._decode(dict(row))
        from backend.app.schemas.memory.values import SOURCE_CATEGORIES
        result['source_categories'] = [kind for kind in result['source_categories'] if kind in SOURCE_CATEGORIES]
        return result

    def _schedule_business_memory_status(self, connection, access, batch):
        from backend.app.repositories.memory.processing.staging_scope import staging
        if staging(self) is not None:
            return
        from backend.app.repositories.business_memory_status_repository import BusinessMemoryStatusRepository
        keys = {(row.source_database, row.change_id) for row in batch.attempts
            if row.source_database and row.task_kind in {'event_formation', 'intake_review'}}
        for status in batch.attempt_updates:
            row = connection.execute("SELECT source_database,change_id FROM processing_attempts WHERE attempt_id=? "
                "AND account_id=? AND member_id=? AND task_kind IN ('event_formation','intake_review')",
                (status.attempt_id, access.account_id, access.member_id)).fetchone()
            if row and row[0]:
                keys.add(tuple(row))
        if not keys and not batch.settings:
            return
        def synchronize():
            repository = BusinessMemoryStatusRepository(self.paths)
            if batch.settings:
                repository.apply_settings(access.account_id, access.member_id)
            repository.sync(access.account_id, access.member_id, keys)
        connection.after_commit(('business_memory_status', access.member_id), synchronize)

    def settings(self, actor_account_id, member_id):
        with self._transaction(actor_account_id, member_id) as (access, connection):
            result = self._settings(connection, access)
            return result




    def _decode(self, row):
        for name in tuple(row):
            if name.endswith("_json"):
                value = row.pop(name)
                row[name[:-5]] = json.loads(value) if value is not None else None
        if 'account_id' in row and 'member_id' in row:
            from backend.app.storage.memory.payloads import payload_has_references
            for field in ('details', 'payload'):
                if isinstance(row.get(field), dict) and payload_has_references(row[field], request=field == 'payload'):
                    row[field] = self.payload_store(row['account_id'], row['member_id']).decode(row[field], request=field == 'payload')
        return row

    def payload_store(self, account, member):
        from backend.app.storage.memory.payloads import MemoryPayloadStore
        return MemoryPayloadStore(self.paths, account, member)

    def _record(self, connection, access, object_type, object_id, *, cutoff=None, item_id=None, version=None, include_payload=True):
        if connection is None or object_type not in MEMORY_OBJECTS:
            return None
        cache = current_read_cache(connection, access)
        cache_key = (object_type, object_id, version, item_id, cutoff)
        if cache is not None and cache_key in cache.rows:
            cache.rows.move_to_end(cache_key)
            # SQLite values are immutable scalars. Parse JSON into fresh values
            # so mutable projections never alter another read's cached row.
            raw = cache.rows[cache_key]
            return self._record_value(raw, object_type, include_payload=include_payload) if raw is not None else None
        table, primary = MEMORY_OBJECTS[object_type]
        where, args = "o.account_id=? AND o.member_id=?", [access.account_id, access.member_id]
        if object_type in VERSION_REFERENCES:
            parent, field = VERSION_REFERENCES[object_type]
            where += f" AND o.{parent}=? AND o.{field}=?"
            args += [object_id, version]
        elif object_type in DETAIL_REFERENCES:
            parent, detail = DETAIL_REFERENCES[object_type]
            where += f" AND o.{parent}=? AND o.{detail}=?"
            args += [object_id, item_id]
        else:
            where += f" AND o.{primary}=?"
            args.append(object_id)
        if cutoff is not None:
            where += " AND c.sequence<=?"
            args.append(cutoff)
        from backend.app.repositories.memory.reading.prepared_reads import prepared_reads, prepared_row_key
        prepared = prepared_reads(self, access)
        prepared_key = prepared_row_key(access, object_type, object_id, version, item_id)
        if prepared is not None and prepared_key in prepared.rows:
            raw = prepared.rows[prepared_key]
            mutable = MEMORY_DATABASE_SCHEMA.table_by_name[table].mutable_columns
            if not mutable:
                # Successful immutable reads/writes remain the same for this
                # execution. Authorization is checked separately by _require.
                if cutoff is not None and raw['record_sequence'] > cutoff:
                    return None
                if cache is not None:
                    cache.save(cache.rows, cache_key, raw, MAX_ROWS)
                return self._record_value(raw, object_type, include_payload=include_payload)
            # Processing state may change through cancellation or another owner.
            columns = ','.join('o.' + field for field in ('commit_id', *mutable))
            current = connection.execute(
                f"SELECT {columns} FROM {table} o JOIN commits c USING(commit_id) WHERE {where}", args).fetchone()
            if current is None:
                return None
            if current['commit_id'] == raw['commit_id']:
                raw = {**raw, **dict(current)}
                if cache is not None:
                    cache.save(cache.rows, cache_key, raw, MAX_ROWS)
                return self._record_value(raw, object_type, include_payload=include_payload)
        row = connection.execute(
            f"SELECT o.*, c.sequence AS record_sequence, c.submitted_at FROM {table} o JOIN commits c USING(commit_id) WHERE {where}", args,
        ).fetchone()
        if row is None:
            if cache is not None:
                cache.save(cache.rows, cache_key, None, MAX_ROWS)
            return None
        raw = dict(row)
        if prepared is not None and cache is not None:
            # Publish only after the transaction succeeds. Validation may read
            # newly inserted rows that are still subject to rollback.
            connection.after_commit(('memory_prepared_read', prepared_key),
                lambda: prepared.save(prepared.rows, prepared_key, raw, MAX_ROWS))
        if cache is not None:
            cache.save(cache.rows, cache_key, raw, MAX_ROWS)
        return self._record_value(raw, object_type, include_payload=include_payload)

    def _record_value(self, raw, object_type, *, include_payload=True):
        raw = dict(raw)
        if object_type == 'memory_execution_entry' and not include_payload:
            payload = json.loads(raw['payload_json'])
            raw['payload_json'] = json.dumps({key: payload[key] for key in ('source_dependencies',) if key in payload})
        value = self._decode(raw)
        value["object_type"] = object_type
        return value

    def _recheck_read_sources(self, connection, access, cache):
        from backend.app.repositories.memory.sources.evidence import check_change
        for reference in list(cache.checked_changes.values()):
            check_change(self,access,reference,connection)

    def _visible(self, connection, access, row):
        if row is None:
            return False
        if row['object_type'] in {'memory_execution_entry'}:
            from backend.app.repositories.memory.processing.execution import execution_visible
            if not execution_visible(self, connection, access, row):
                return False
        member_deleted = connection.execute("SELECT 1 FROM access_restrictions WHERE account_id=? AND member_id=? AND restriction_kind='member_deleted' LIMIT 1", (access.account_id, access.member_id)).fetchone()
        if member_deleted:
            return False
        from backend.app.repositories.memory.sources.evidence import change_references, check_change
        try:
            for reference in change_references(self, connection, access, row):
                check_change(self, access, reference, connection)
        except SerenitaError as error:
            if error.kind in {'missing', 'forbidden'}:
                return False
            raise
        return True

    def _require(self, connection, access, object_type, object_id, *, cutoff=None, item_id=None, version=None):
        row = self._record(connection, access, object_type, object_id, cutoff=cutoff, item_id=item_id, version=version)
        if not self._visible(connection, access, row):
            _error("missing", "MEMORY_OBJECT_UNAVAILABLE", "记忆对象不存在或当前不可访问。")
        return row

    @staticmethod
    def _insert(connection, table_name, row):
        table = MEMORY_DATABASE_SCHEMA.table_by_name[table_name]
        table.validate_values(row)
        if table_name == 'processing_steps':
            # Progress is a replaceable snapshot, scoped to one attempt and step.
            # The enclosing transaction rolls back the deletion on any failure.
            connection.execute('DELETE FROM processing_steps WHERE account_id=? AND member_id=? '
                'AND attempt_id=? AND step_id=? AND parent_step_id IS ?',
                (row['account_id'], row['member_id'], row['attempt_id'], row['step_id'], row['parent_step_id']))
        connection.execute(f"INSERT INTO {table_name} ({','.join(table.column_names)}) VALUES ({','.join('?' for _ in table.columns)})", tuple(row.get(name) for name in table.column_names))

    def _encode(self, collection, item, scope_values, *, table_name=None):
        row = {**item.model_dump(mode="json"), **scope_values}
        if collection == "attempts":
            row.update(model_id=None, result_references=[],
                outcome_reason=None, gaps=[], processing_status='pending', error_code=None,
                error_message=None, retry_after=None, started_commit_id=None, updated_commit_id=row['commit_id'])
        if collection == "events":
            from backend.app.domain.memory.event_text import event_text
            row["text_hash"] = hashlib.sha256(event_text(row).encode("utf-8")).hexdigest()
        table_name = table_name or MEMORY_COLLECTIONS[collection][0]
        columns = MEMORY_DATABASE_SCHEMA.table_by_name[table_name].column_names
        if collection == "semantic_vector_bindings":
            if row.pop("index_kind") == "entity_role":
                row.pop("name_id")
            else:
                row.pop("event_id")
        for name in columns:
            if name.endswith("_json"):
                value = row.pop(name[:-5])
                if collection in {'processing_steps', 'execution_entries'} and name in {'details_json', 'payload_json'}:
                    value = self.payload_store(row['account_id'], row['member_id']).encode(value, request=name == 'payload_json')
                row[name] = _canonical(value) if value is not None else None
        return row

    def _commit_result(self, connection, commit, *, replayed, access, written=None):
        commit = dict(commit)
        objects = {}
        from backend.app.repositories.memory.reading.prepared_reads import prepared_reads, prepared_row_key
        prepared = prepared_reads(self, access)
        confirmed_rows = {}
        for collection, (table, kind, primary) in MEMORY_COLLECTIONS.items():
            if kind is None:
                continue
            rows = (connection.execute(f"SELECT * FROM {table} WHERE commit_id=? ORDER BY {primary}", (commit["commit_id"],)).fetchall()
                    if written is None else sorted(written.get(collection, []), key=lambda row: row[primary]))
            if rows:
                objects[kind] = []
                for row in rows:
                    value = {"object_type": kind, "object_id": row[primary]}
                    if kind in VERSION_REFERENCES:
                        parent, field = VERSION_REFERENCES[kind]
                        value.update(object_id=row[parent], version=row[field])
                    elif kind in DETAIL_REFERENCES:
                        parent, detail = DETAIL_REFERENCES[kind]
                        value.update(object_id=row[parent], item_id=row[detail])
                    objects[kind].append(value)
                    if prepared is not None:
                        key = prepared_row_key(access, kind, value['object_id'], value.get('version'), value.get('item_id'))
                        confirmed_rows[key] = {**dict(row), 'record_sequence': commit['sequence'], 'submitted_at': commit['submitted_at']}
        if confirmed_rows:
            def retain_committed():
                for key, row in confirmed_rows.items():
                    prepared.save(prepared.rows, key, row, MAX_ROWS)
            connection.after_commit(('memory_prepared_rows', commit['commit_id']), retain_committed)
        return {"commit_id": commit["commit_id"], "sequence": commit["sequence"], "operation_id": commit["operation_id"], "submitted_at": commit["submitted_at"], "objects": objects, "replayed": replayed}


    def write(self, actor_account_id, member_id, operation_id, batch, *, command=None, extraction_mentions=None, return_attempts=False):
        from backend.app.repositories.memory.processing.staging_scope import staging
        draft = staging(self, actor_account_id, member_id)
        options = dict(command=command, extraction_mentions=extraction_mentions, return_attempts=return_attempts)
        if draft is not None:
            return draft.write(operation_id, batch, **options)
        return self._write(actor_account_id, member_id, operation_id, batch, **options)

    def _write(self, actor_account_id, member_id, operation_id, batch, *, command=None, extraction_mentions=None, return_attempts=False):
        if not isinstance(batch, MemoryWrite):
            batch = MemoryWrite.model_validate(batch)
        if extraction_mentions is not None and set(extraction_mentions) != {event.event_id for event in batch.events}:
            _error("invalid_input", "MEMORY_EXTRACTION_SCOPE_INVALID", "提取实体的核对范围必须与本次追加事件一致。")
        if not isinstance(operation_id, str) or not operation_id.strip() or len(operation_id) > 512:
            _error("invalid_input", "MEMORY_INVALID_OPERATION", "追加操作标识必须为非空且不超过 512 字符的字符串。")
        request_hash = _digest({"actor_account_id": actor_account_id, "member_id": member_id, "request": command if command is not None else batch.model_dump(mode="json")})
        from backend.app.repositories.memory.processing.execution import execution_validation_scope
        try:
            with self._transaction(actor_account_id, member_id, write=True) as (access, connection), execution_validation_scope(connection):
                if batch.settings and access.permission != "owner":
                    _error("forbidden", "MEMORY_SETTINGS_OWNER_ONLY", "只有健康档案所有者可以保存记忆形成设置。")
                if batch.restrictions:
                    _error("forbidden", "MEMORY_RESTRICTION_CAPABILITY", "访问限制仅由应用权限生命周期入口追加。")
                deleted = connection.execute("SELECT 1 FROM access_restrictions WHERE account_id=? AND member_id=? AND restriction_kind='member_deleted' LIMIT 1", (access.account_id, member_id)).fetchone()
                if deleted:
                    _error("forbidden", "MEMORY_MEMBER_RESTRICTED", "当前成员的记忆已限制访问。")
                existing = connection.execute("SELECT * FROM commits WHERE account_id=? AND member_id=? AND operation_id=?", (access.account_id, member_id, operation_id)).fetchone()
                if existing is not None:
                    if existing["request_hash"] != request_hash:
                        _error("conflict", "MEMORY_OPERATION_CONFLICT", "相同操作标识的追加参数与原请求不一致。")
                    result = self._commit_result(connection, existing, replayed=True, access=access)
                    # Replaying a former successful write must not reveal ids
                    # that became inaccessible after source deletion.
                    for references in result["objects"].values():
                        for reference in references:
                            self._require(connection, access, reference["object_type"], reference["object_id"], item_id=reference.get("item_id"), version=reference.get("version"))
                    if batch.semantic_vector_bindings or batch.semantic_vector_statuses:
                        from backend.app.repositories.memory.indexing.semantic_index_repository import require_binding
                        for item in [*batch.semantic_vector_bindings, *batch.semantic_vector_statuses]:
                            require_binding(self, connection, access, item.binding_id)
                    if batch.chunk_vector_bindings or batch.chunk_vector_statuses:
                        from backend.app.repositories.memory.indexing.chunk_index_repository import require_binding
                        for item in [*batch.chunk_vector_bindings, *batch.chunk_vector_statuses]:
                            require_binding(self, connection, access, item.binding_id)
                    self._schedule_business_memory_status(connection, access, batch)
                    for item in batch.attempt_updates:
                        self._require(connection, access, 'processing_attempt', item.attempt_id)
                        refs = result['objects'].setdefault('processing_attempt', [])
                        ref = {'object_type': 'processing_attempt', 'object_id': item.attempt_id}
                        if ref not in refs: refs.append(ref)
                    if return_attempts:
                        result['attempts'] = [self._project(connection, access,
                            self._require(connection, access, 'processing_attempt', identity), self._cutoff(connection, access))
                            for identity in dict.fromkeys([item.attempt_id for item in [*batch.attempts, *batch.attempt_updates]])]
                    return result
                settings = self._settings(connection, access)
                controls_only = not batch.attempt_updates and not any(getattr(batch, key) for key in MEMORY_COLLECTIONS if key not in {"settings", "restrictions"})
                stopping_only = bool(batch.attempt_updates) and all(item.processing_status in {'cancelled', 'failed'} for item in batch.attempt_updates) and not any(
                    getattr(batch, key) for key in MEMORY_COLLECTIONS if key != 'attempt_updates')
                from backend.app.repositories.memory.processing.execution import check_execution_write, execution_settlement_only
                settlement_only = execution_settlement_only(self, connection, access, batch)
                if not controls_only and not stopping_only and not settlement_only and settings["formation_state"] != "enabled":
                    _error("forbidden", "MEMORY_FORMATION_PAUSED" if settings["formation_state"] == "paused" else "MEMORY_FORMATION_DISABLED", "当前范围的自动记忆形成已暂停或尚未开启。")
                check_execution_write(self, connection, access, batch, settlement_only=settlement_only)
                self._check_chains(connection, access, batch)
                from backend.app.repositories.memory.processing.attempts import validate_updates, apply_updates
                validate_updates(self, connection, access, batch)
                from backend.app.repositories.memory.facts.relations import validate_relation_pairs, validate_relation_append
                validate_relation_pairs(self, connection, access, batch)
                from backend.app.repositories.memory.facts.episodes import validate_membership_uniqueness
                validate_membership_uniqueness(connection, access, batch)
                before_cutoff = self._cutoff(connection, access)
                sequence = connection.execute("SELECT COALESCE(max(sequence),0)+1 FROM commits").fetchone()[0]
                submitted_at = _now()
                commit = {"commit_id": stable_memory_id(member_id, operation_id, "commit", "commit"), "account_id": access.account_id, "member_id": member_id,
                          "actor_account_id": actor_account_id, "operation_id": operation_id, "request_hash": request_hash, "sequence": sequence, "submitted_at": submitted_at}
                self._insert(connection, "commits", commit)
                shared = {key: commit[key] for key in ("account_id", "member_id", "commit_id")}
                written = {}
                for collection, (table, _, _) in MEMORY_COLLECTIONS.items():
                    for item in getattr(batch, collection):
                        if collection == "attempts":
                            if item.input_sequence > before_cutoff:
                                _error("invalid_input", "MEMORY_INVALID_INPUT_CUTOFF", "计算输入截点不能包含尚未成功提交的内容。")
                            if item.previous_attempt_id:
                                previous = self._require(connection, access, "processing_attempt", item.previous_attempt_id)
                                if item.task_kind == "event_formation":
                                    if any(previous[key] != getattr(item, key) for key in (
                                            "task_kind", "source_account_id", "source_database", "change_id", "change_sequence")):
                                        _error("invalid_input", "MEMORY_FORMATION_RETRY_SCOPE", "事件形成重试必须承接同一业务变更。")
                                    completed_change = connection.execute("SELECT 1 FROM processing_attempts WHERE account_id=? AND member_id=? "
                                        "AND task_kind='event_formation' AND source_database IS ? AND change_id IS ? "
                                        "AND processing_status='completed' LIMIT 1", (access.account_id, member_id, item.source_database, item.change_id)).fetchone()
                                    if completed_change:
                                        _error("conflict", "MEMORY_FORMATION_RETRY_STATE", "这条变更记录已经全部处理完成，不能重试。")
                                    successor = connection.execute("SELECT 1 FROM processing_attempts WHERE previous_attempt_id=? LIMIT 1",
                                        (item.previous_attempt_id,)).fetchone()
                                    if successor:
                                        _error("conflict", "MEMORY_FORMATION_RETRY_STATE", "此处理已有后续尝试，不能重复启动；请查看最新处理结果。")
                                    state = self._project(connection, access, previous, before_cutoff)
                                    if state.get("processing_status") not in {"failed", "cancelled"}:
                                        _error("conflict", "MEMORY_FORMATION_RETRY_STATE", "只有失败或已取消的事件形成任务可以重试。")
                                if item.task_kind == "intake_review" and item.source_account_id:
                                    if any(previous[key] != getattr(item, key) for key in ("task_kind", "source_account_id", "source_database", "change_id", "change_sequence")):
                                        _error("invalid_input", "MEMORY_DELIVERY_RETRY_IDENTITY", "交付重试必须承接同一来源变化。")
                                    state = self._project(connection, access, previous, before_cutoff)
                                    if state.get("processing_status") != "failed":
                                        _error("conflict", "MEMORY_DELIVERY_RETRY_STATE", "仅已失败的交付尝试可以创建重试。")
                        target_table = table
                        if isinstance(table, tuple):
                            from backend.app.repositories.memory.indexing.semantic_index_repository import append_table
                            target_table = append_table(self, connection, access, collection, item)
                        encoded = self._encode(collection, item, shared, table_name=target_table)
                        self._insert(connection, target_table, encoded)
                        written.setdefault(collection, []).append(encoded)
                updated_attempts = apply_updates(self, connection, access, batch, commit)
                if written.get('attempts'):
                    written['attempts'] = [updated_attempts.get(row['attempt_id'], row) for row in written['attempts']]
                with self._saved_read_scope(connection, access, written, commit):
                    self._check_evidence(connection, access, batch)
                    validate_relation_append(self, connection, access, batch)
                    from backend.app.repositories.memory.facts.episodes import validate_episode_append
                    validate_episode_append(self, connection, access, batch, before_cutoff)
                    if batch.execution_entries:
                        from backend.app.repositories.memory.processing.execution import validate_execution_append
                        validate_execution_append(self, connection, access, batch, before_cutoff)
                    from backend.app.storage.memory.index_database import MEMORY_INDEX_COLLECTIONS
                    if any(getattr(batch, key) for key in MEMORY_INDEX_COLLECTIONS):
                        from backend.app.repositories.memory.indexing.index_repository import validate_index_append
                        validate_index_append(self, connection, access, batch, extraction_mentions=extraction_mentions)
                    if batch.semantic_vector_bindings or batch.semantic_vector_statuses:
                        from backend.app.repositories.memory.indexing.semantic_index_repository import validate_semantic_index_append
                        validate_semantic_index_append(self, connection, access, batch)
                    if batch.chunk_vector_bindings or batch.chunk_vector_statuses:
                        from backend.app.repositories.memory.indexing.chunk_index_repository import validate_chunk_index_append
                        validate_chunk_index_append(self, connection, access, batch)
                    for status in batch.attempt_updates:
                        for reference in status.result_references:
                            self._require(connection, access, reference.object_type, reference.object_id, item_id=reference.item_id, version=reference.version)
                    self._validate_appended_categories(connection, access, batch, settings)
                    # Every exposed object inherits its actual evidence permissions.
                    for collection, (_, kind, primary) in MEMORY_COLLECTIONS.items():
                        if kind is None or kind == "access_restriction":
                            continue
                        for item in getattr(batch, collection):
                            if kind in VERSION_REFERENCES:
                                parent, field = VERSION_REFERENCES[kind]
                                self._require(connection, access, kind, getattr(item, parent), version=getattr(item, field))
                            elif kind in DETAIL_REFERENCES:
                                parent, detail = DETAIL_REFERENCES[kind]
                                self._require(connection, access, kind, getattr(item, parent, member_id), item_id=getattr(item, detail))
                            else:
                                self._require(connection, access, kind, getattr(item, primary))
                    self._schedule_business_memory_status(connection, access, batch)
                    result = self._commit_result(connection, commit, replayed=False, access=access, written=written)
                    from backend.app.repositories.memory.reading.prepared_reads import prepared_reads
                    prepared = prepared_reads(self, access)
                    if prepared is not None:
                        from backend.app.repositories.memory.reading.episode_context import advance_episode_contexts
                        connection.after_commit(('memory_episode_contexts', commit['commit_id']),
                            lambda: advance_episode_contexts(prepared, access, written, before_cutoff, commit))
                    for item in batch.attempt_updates:
                        refs = result['objects'].setdefault('processing_attempt', [])
                        ref = {'object_type': 'processing_attempt', 'object_id': item.attempt_id}
                        if ref not in refs: refs.append(ref)
                    if return_attempts:
                        attempts = {row['attempt_id']: {**row, 'record_sequence': sequence, 'submitted_at': submitted_at}
                                    for row in written.get('attempts', [])}
                        attempts.update(updated_attempts)
                        result['attempts'] = [self._project(connection, access, self._record_value(row, 'processing_attempt'), sequence)
                                              for row in attempts.values()]
                    return result
        except sqlite3.IntegrityError:
            _error("conflict", "MEMORY_APPEND_CONFLICT", "记忆追加的标识、引用或承接与当前保存内容冲突。")

    @contextmanager
    def _saved_read_scope(self, connection, access, written, commit):
        # All mutations are complete. Reuse fixed rows only for validation in
        # this transaction; a rollback or the next transaction discards them.
        with immutable_read_scope(connection, access, write=False) as cache:
            for collection, rows in written.items():
                _, kind, primary = MEMORY_COLLECTIONS[collection]
                if kind is None:
                    continue
                for row in rows:
                    identity, version, item = row[primary], None, None
                    if kind in VERSION_REFERENCES:
                        parent, field = VERSION_REFERENCES[kind]
                        identity, version = row[parent], row[field]
                    elif kind in DETAIL_REFERENCES:
                        parent, field = DETAIL_REFERENCES[kind]
                        identity, item = row[parent], row[field]
                    raw = {'record_sequence': commit['sequence'], 'submitted_at': commit['submitted_at'], **row}
                    cache.save(cache.rows, (kind, identity, version, item, None), raw, MAX_ROWS)
            yield
            self._recheck_read_sources(connection, access, cache)

    def _validate_appended_categories(self, connection, access, batch, settings):
        categories = set()
        for collection, (_, kind, primary) in MEMORY_COLLECTIONS.items():
            if kind is None or kind in {"access_restriction", "memory_setting"}:
                continue
            for item in getattr(batch, collection):
                if kind in VERSION_REFERENCES:
                    parent, field = VERSION_REFERENCES[kind]
                    row = self._record(connection, access, kind, getattr(item, parent), version=getattr(item, field))
                elif kind in DETAIL_REFERENCES:
                    parent, detail = DETAIL_REFERENCES[kind]
                    row = self._record(connection, access, kind, getattr(item, parent), item_id=getattr(item, detail))
                else:
                    row = self._record(connection, access, kind, getattr(item, primary))
                from backend.app.repositories.memory.sources.evidence import evidence_categories
                categories.update(evidence_categories(self,connection,access,row))
        from backend.app.repositories.memory.sources.evidence import read_change
        for item in batch.event_evidence:
            categories.add(read_change(self,access,item.model_dump(exclude={'event_id'}),connection)['source_category'])
        if not categories.issubset(set(settings["source_categories"])):
            _error("forbidden", "MEMORY_SOURCE_SCOPE_DISABLED", "新增内容的实际依据包含尚未获准形成记忆的来源范围。")


    def _check_chains(self, connection, access, batch):
        if len(batch.settings) > 1:
            _error("invalid_input", "MEMORY_SETTINGS_BATCH", "同次提交只能保存一条当前设置。")
        for setting in batch.settings:
            current = self._settings(connection, access)
            if setting.previous_setting_id != current["setting_id"]:
                _error("conflict", "MEMORY_SETTINGS_CONFLICT", "形成设置已变化，请读取后重新判断。")
    def _check_evidence(self, connection, access, batch):
        from backend.app.repositories.memory.sources.evidence import read_change
        new_events = {event.event_id for event in batch.events}
        for link in batch.event_evidence:
            if link.event_id not in new_events:
                _error('invalid_input', 'MEMORY_REFERENCE_IMMUTABLE', '事件依据必须与事件共同追加。')
            read_change(self, access, link.model_dump(exclude={'event_id'}), connection)
        for event in batch.events:
            if not any(link.event_id == event.event_id for link in batch.event_evidence):
                _error('invalid_input', 'MEMORY_EVENT_EVIDENCE_REQUIRED', '新事件必须共同保存业务变更引用。')
    _time_bounds = staticmethod(memory_time_bounds)

    def _matches(self, connection, access, row, query):
        if query.source_categories:
            categories = set()
            from backend.app.repositories.memory.sources.evidence import change_references, read_change
            categories.update(read_change(self,access,ref,connection)['source_category']
                for ref in change_references(self,connection,access,row))
            if not categories.intersection(query.source_categories):
                return False
        if query.query and query.query.casefold() not in _canonical(row).casefold():
            return False
        if query.target_time is not None:
            target_start, target_end = self._time_bounds(query.target_time)
            start, end = occurrence_time_bounds(row.get("occurrence_time")) if row["object_type"] == "event" else self._time_bounds(row.get("occurrence_time"))
            if target_end is not None and start is not None and start > target_end:
                return False
            if target_start is not None and end is not None and end < target_start:
                return False
        return True

    def _project(self, connection, access, row, cutoff, query=None, *, include_execution_entries=True):
        kind = row["object_type"]
        if kind in EPISODE_KINDS:
            from backend.app.repositories.memory.facts.episodes import project_episode
            return project_episode(self, connection, access, row, cutoff)
        if kind in {"event_relation"}:
            from backend.app.repositories.memory.facts.relations import project_relation_object
            return project_relation_object(self, connection, access, row, cutoff)
        if kind == "event":
            from backend.app.repositories.memory.facts.event_evidence import event_references
            row['evidence'] = event_references(connection, access, row['event_id'])
            links = connection.execute(
                "SELECT l.event_id,l.entity_id,l.description FROM event_entities l "
                "JOIN commits c USING(commit_id) "
                "WHERE l.account_id=? AND l.member_id=? AND l.event_id=? AND c.sequence<=? "
                "ORDER BY l.entity_id", (access.account_id, access.member_id, row["event_id"], cutoff))
            row["event_associations"] = []
            for link in links:
                entity = self._record(connection, access, "entity", link["entity_id"], cutoff=cutoff)
                if self._visible(connection, access, entity):
                    row["event_associations"].append(dict(link))
            row["entity_ids"] = [item["entity_id"] for item in row["event_associations"]]
        elif kind == "entity":
            names = connection.execute(
                "SELECT n.name_id FROM entity_names n JOIN commits c USING(commit_id) "
                "WHERE n.account_id=? AND n.member_id=? AND n.entity_id=? AND c.sequence<=? ORDER BY n.name_id",
                (access.account_id, access.member_id, row["entity_id"], cutoff))
            values = [self._record(connection, access, "entity_name", row["entity_id"], item_id=item["name_id"], cutoff=cutoff) for item in names]
            row["names"] = [value for value in values if self._visible(connection, access, value)]
        elif kind == "vector_binding":
            status = connection.execute(
                "SELECT v.status_id FROM event_vector_statuses v JOIN commits c USING(commit_id) "
                "WHERE v.account_id=? AND v.member_id=? AND v.binding_id=? AND c.sequence<=? "
                "AND NOT EXISTS (SELECT 1 FROM event_vector_statuses n JOIN commits nc ON nc.commit_id=n.commit_id "
                "WHERE n.binding_id=v.binding_id AND n.previous_status_id=v.status_id AND nc.sequence<=?)",
                (access.account_id, access.member_id, row["binding_id"], cutoff, cutoff)).fetchone()
            value = self._record(connection, access, "vector_status", row["binding_id"], item_id=status["status_id"], cutoff=cutoff) if status else None
            row["status"] = value if self._visible(connection, access, value) else None
        elif kind == "processing_attempt":
            latest_update = connection.execute('SELECT sequence, submitted_at FROM commits WHERE commit_id=?', (row['updated_commit_id'],)).fetchone()
            if query is not None and (query.view != 'current' or query.record_cutoff is not None and query.record_cutoff < latest_update['sequence']):
                _error('invalid_input', 'MEMORY_PROCESSING_HISTORY_UNSUPPORTED', '处理记录只保存最新情况，不能读取历史运行状态。')
            row['updated_at'] = latest_update['submitted_at']
            if any(not self._visible(connection, access, self._record(connection, access, ref['object_type'], ref['object_id'], item_id=ref.get('item_id'), version=ref.get('version'))) for ref in row['result_references']):
                row.update(processing_status=None, result_references=[], outcome_reason=None, gaps=[], error_code=None, error_message=None, retry_after=None)
            if row['started_commit_id']:
                row['started_at'] = connection.execute('SELECT submitted_at FROM commits WHERE commit_id=?', (row['started_commit_id'],)).fetchone()[0]
            if not include_execution_entries:
                return row
            entries = connection.execute("SELECT e.attempt_id,e.entry_id,e.account_id,e.member_id,e.commit_id,e.dependencies_json, "
                "json_object('source_dependencies',json(COALESCE(json_extract(e.payload_json,'$.source_dependencies'),'[]'))) AS payload_json "
                'FROM execution_entries e JOIN commits c USING(commit_id) WHERE e.attempt_id=? AND c.sequence<=? ORDER BY e.entry_sequence',
                (row['attempt_id'], cutoff)).fetchall()
            row['entry_references'] = [{'object_type': 'memory_execution_entry', 'object_id': row['attempt_id'], 'item_id': entry['entry_id']}
                for entry in entries if self._visible(connection, access, self._record_value(entry, 'memory_execution_entry'))]
            row['restricted_entries'] = len(entries) - len(row['entry_references'])
        return row

    def _observation(self, access, query, cutoff, objects, *, total, next_cursor=None):
        return {"member_id": access.member_id, "record_cutoff": cutoff, "target_time": query.target_time.model_dump(mode="json") if query.target_time else None,
                "view": query.view, "objects": objects, "relations": [], "coverage": {"matching_objects": total, "returned_objects": len(objects), "complete": next_cursor is None, "object_types": query.object_types},
                "gaps": [], "unread": [], "next_cursor": next_cursor, "continuations": [], "processing_status": None}

    @staticmethod
    def _row_key(row):
        kind = row["object_type"]
        if kind in VERSION_REFERENCES:
            parent, field = VERSION_REFERENCES[kind]
            return (-row["record_sequence"], kind, row[parent], str(row[field]).zfill(20))
        if kind in DETAIL_REFERENCES:
            parent, detail = DETAIL_REFERENCES[kind]
            return (-row["record_sequence"], kind, row[parent], row[detail])
        return (-row["record_sequence"], kind, row[MEMORY_OBJECTS[kind][1]], "")

    def query(self, actor_account_id, member_id, query=None):
        query = query if isinstance(query, MemoryQuery) else MemoryQuery.model_validate(query or {})
        with self._transaction(actor_account_id, member_id) as (access, connection):
            # A cursor carries the original cutoff; validate its scope before
            # accepting it, then retain that snapshot when new commits arrive.
            scope_query = query.model_dump(mode="json", exclude={"cursor", "record_cutoff", "limit"})
            scope = ["memory", access.account_id, member_id, access.permission, access.grant_updated_at.isoformat() if access.grant_updated_at else "owner", scope_query]
            position = seek_position(query.cursor, scope=scope, size=5)
            cutoff = self._cutoff(connection, access, int(position[0]) if position else query.record_cutoff)
            if position and query.record_cutoff is not None and query.record_cutoff != cutoff:
                _error("invalid_input", "MEMORY_CURSOR_SCOPE", "分页游标不属于指定记录截点。")
            last_key = None
            if position:
                try:
                    last_key = (-int(position[1]), position[2], position[3], position[4])
                    if int(position[1]) < 1 or position[2] not in MEMORY_OBJECTS:
                        raise ValueError()
                    canonical_uuid(position[3])
                    if position[2] in VERSION_REFERENCES:
                        if not position[4].isdigit() or int(position[4]) < 1:
                            raise ValueError()
                    elif position[2] in DETAIL_REFERENCES:
                        canonical_uuid(position[4])
                    elif position[4] != "":
                        raise ValueError()
                except (TypeError, ValueError):
                    _error("invalid_input", "MEMORY_CURSOR_SCOPE", "分页游标无效。")
            rows = []
            if connection is not None:
                for kind in query.object_types:
                    table, primary = MEMORY_OBJECTS[kind]
                    found = connection.execute(
                        f"SELECT o.*, c.sequence AS record_sequence, c.submitted_at FROM {table} o JOIN commits c USING(commit_id) WHERE o.account_id=? AND o.member_id=? AND c.sequence<=?",
                        (access.account_id, member_id, cutoff)).fetchall()
                    decoded = []
                    for raw in found:
                        row = self._decode(dict(raw))
                        row["object_type"] = kind
                        decoded.append(row)
                    for row in decoded:
                        if self._visible(connection, access, row) and self._matches(connection, access, row, query):
                            rows.append(row)
            rows.sort(key=self._row_key)
            remaining = rows if last_key is None else [row for row in rows if self._row_key(row) > last_key]
            selected = remaining[:query.limit]
            last = selected[-1] if selected else None
            following = seek_cursor(scope, [str(cutoff), str(last["record_sequence"]), *self._row_key(last)[1:]]) if last and len(remaining) > query.limit else None
            objects = [self._project(connection, access, row, cutoff, query) for row in selected]
            return self._observation(access, query, cutoff, objects, total=len(rows), next_cursor=following)

    def read(self, actor_account_id, member_id, references, query=None):
        query = query if isinstance(query, MemoryQuery) else MemoryQuery.model_validate(query or {})
        refs = [value if isinstance(value, MemoryReference) else MemoryReference.model_validate(value) for value in references]
        if not 1 <= len(refs) <= 100:
            _error("invalid_input", "MEMORY_REFERENCE_LIMIT", "每次读取必须提供 1 至 100 个明确对象引用。")
        with self._transaction(actor_account_id, member_id) as (access, connection):
            cutoff = self._cutoff(connection, access, query.record_cutoff)
            objects = []
            for reference in refs:
                row = self._require(connection, access, reference.object_type, reference.object_id, cutoff=cutoff, item_id=reference.item_id, version=reference.version)
                objects.append(self._project(connection, access, row, cutoff, query))
            return self._observation(access, query, cutoff, objects, total=len(objects))

    def read_processing_attempt(self, actor_account_id, member_id, attempt_id):
        """Read current task state without enumerating its model stream history."""
        with self._transaction(actor_account_id, member_id) as (access, connection):
            cutoff = self._cutoff(connection, access)
            row = self._require(connection, access, 'processing_attempt', attempt_id, cutoff=cutoff)
            return self._project(connection, access, row, cutoff, include_execution_entries=False)

    def check_references(self, actor_account_id, member_id, references, *, record_cutoff=None):
        """Check live access without building display projections or returning bodies."""
        refs = [MemoryReference.model_validate(value) for value in references]
        if len(refs) > MAX_ROWS:
            _error('resource_limit', 'MEMORY_STAGE_INPUT_LIMIT', '访问检查超过对象预算。')
        with self._transaction(actor_account_id, member_id) as (access, connection):
            cutoff = self._cutoff(connection, access, record_cutoff)
            for reference in refs:
                self._require(connection, access, reference.object_type, reference.object_id,
                    cutoff=cutoff, item_id=reference.item_id, version=reference.version)
        return {'record_cutoff': cutoff, 'references': [ref.model_dump(mode='json') for ref in refs]}

    def read_facts(self, actor_account_id, member_id, references, *, record_cutoff=None):
        """Read immutable facts for background inputs, without display projections."""
        query = MemoryQuery(record_cutoff=record_cutoff)
        refs = [MemoryReference.model_validate(value) for value in references]
        if not 1 <= len(refs) <= 100:
            _error('invalid_input', 'MEMORY_REFERENCE_LIMIT', '每次读取必须提供 1 至 100 个明确对象引用。')
        with self._transaction(actor_account_id, member_id) as (access, connection):
            cutoff = self._cutoff(connection, access, record_cutoff)
            objects = []
            from backend.app.repositories.memory.facts.event_evidence import event_references
            from backend.app.repositories.memory.reading.prepared_reads import prepared_reads, prepared_row_key
            prepared = prepared_reads(self, access)
            reused = []
            for ref in refs:
                key = prepared_row_key(access, ref.object_type, ref.object_id, ref.version, ref.item_id)
                if prepared is not None and key in prepared.rows:
                    reused.append(ref.model_dump(mode='json'))
                row = self._require(connection, access, ref.object_type, ref.object_id,
                    cutoff=cutoff, item_id=ref.item_id, version=ref.version)
                if ref.object_type == 'event':
                    row['evidence'] = event_references(connection, access, ref.object_id)
                objects.append(row)
            result = self._observation(access, query, cutoff, objects, total=len(objects))
            result['reused_references'] = reused
            return result

    def execution_status(self, actor_account_id, member_id, attempt_id, *, source_reference=None):
        """Read only the current execution state under the member write permission."""
        with self.members.access_guard(actor_account_id, member_id, write=True):
            with self._transaction(actor_account_id, member_id) as (access, connection):
                row = connection.execute('SELECT processing_status, model_id FROM processing_attempts '
                    'WHERE account_id=? AND member_id=? AND attempt_id=?',
                    (access.account_id, member_id, attempt_id)).fetchone() if connection is not None else None
                if row is None:
                    _error('missing', 'MEMORY_OBJECT_UNAVAILABLE', '处理任务不存在或当前不可访问。')
                if source_reference is not None:
                    from backend.app.repositories.memory.sources.evidence import check_change
                    check_change(self, access, source_reference, connection)
                return dict(row)
