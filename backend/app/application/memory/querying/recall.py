"""Recall indexed memory, rank matching results and apply occurrence-time filters."""
from __future__ import annotations
from backend.app.application.memory.progress import track_step

from copy import deepcopy
import time

from backend.app.core.errors import SerenitaError
from backend.app.core.cancellation import OperationCancelledError
from backend.app.repositories.memory.indexing.index_repository import MemoryIndexRepository
from backend.app.domain.memory.vectors import fail
from backend.app.schemas.memory.append import MemoryQuery
from backend.app.schemas.memory.index import IndexSearchInput


BUDGETS = {"seed_each": 20, "hops": 2, "events": 64, "entities": 32, "candidates": 32, "selected": 12}




from backend.app.application.memory.vector_models import MemoryVectorModels


class MemoryRecallService:
    def __init__(self, memory, *, repository=None, vector_models=None, relation_provider=None,
                 connection_provider=None, expansion_enabled=True, complete_model=None,
                 cancellation_token=None, deadline=None):
        self.memory = memory
        self.repository = repository or MemoryIndexRepository(memory.repository)
        self.vector_models = vector_models or MemoryVectorModels(memory,
            cancellation_token=cancellation_token, deadline=deadline)
        self.models = memory.models
        self.complete_model = complete_model
        self.cancellation_token, self.deadline = cancellation_token, deadline
        if type(expansion_enabled) is not bool:
            raise ValueError('Expansion control must be a boolean')
        self.expansion_enabled = expansion_enabled
        from backend.app.repositories.memory.facts.relations import MemoryRelationRepository
        from backend.app.repositories.memory.indexing.index_connections import event_connections
        self.relation_provider = relation_provider or MemoryRelationRepository(memory.repository).event_groups
        self.connection_provider = connection_provider or (
            lambda actor, member, cutoff, ids: event_connections(memory.repository, actor, member, cutoff, ids))

    def check_running(self):
        self.vector_models.check_running()

    @staticmethod
    def validate_selection(result, event_ids):
        if not isinstance(event_ids, list) or len(event_ids) > BUDGETS["selected"] or len(set(event_ids)) != len(event_ids):
            fail("MEMORY_SELECTION_INVALID", "联合选择必须提供不重复且至多 12 条的事件标识。")
        candidates = {row["event_id"]: row for row in result["candidates"]}
        if any(value not in candidates for value in event_ids):
            fail("MEMORY_SELECTION_INVALID", "只能选择本次实际返回的描述。")
        return [{"object_type": "event", "object_id": candidates[value]["event_id"]} for value in event_ids]

    @track_step('recall')
    def recall(self, actor, member, values):
        self.vector_models.check_running()
        query = IndexSearchInput.model_validate(values)
        repo = self.repository
        stages, failures, gaps = [], [], []
        started = time.monotonic()
        snapshot = repo.snapshot(actor, member, query.record_cutoff)
        resolved_space_id = query.space_id
        if resolved_space_id is None:
            configured_model = self.vector_models.default_model_id(snapshot["account_id"])
            if configured_model:
                try:
                    resolved_space_id = self.vector_models.space(snapshot["account_id"], member, configured_model)["space_id"]
                except SerenitaError as exc:
                    failures.append({"code": exc.code, "message": exc.message})
        scope = {"actor": actor, "account": snapshot["account_id"], "member": member, "query": query.query,
                 "space_id": resolved_space_id, "record_cutoff": snapshot["record_cutoff"],
                 "target_time": query.target_time.model_dump(mode="json") if query.target_time else None,
                 "expansion_enabled": self.expansion_enabled}
        done, resume_paths = set(), {}
        if query.continuation:
            from backend.app.application.memory.querying.search_continuation import decode
            token = decode(scope, query.continuation)
            done, resume_paths = set(token['seen']), token['seed_paths']
        def stage(name, inputs, outputs, **extra):
            nonlocal started
            now = time.monotonic()
            stages.append({"stage": name, "inputs": inputs, "outputs": outputs, "elapsed_ms": round((now - started) * 1000, 3), **extra})
            started = now
        all_events = snapshot["events"]
        descriptions = all_events
        criteria = MemoryQuery(target_time=query.target_time, record_cutoff=snapshot["record_cutoff"])
        if query.target_time is not None:
            times = repo.time_context(actor, member, descriptions, snapshot["record_cutoff"])
            if times["unread"]:
                gaps.append({"code": "time_evaluation_incomplete", "unread": times["unread"]})
            descriptions = repo.filter_event_times(actor, member, descriptions, times, criteria)
        stage("query_representation", 1, 1, record_cutoff=snapshot["record_cutoff"], excluded=snapshot["excluded"])
        from backend.app.repositories.memory.reading.search_hits import (project_hits, hit_lookup,
            ranking_evidence, encoded_size, MAX_TEXT_HITS, MAX_SEED_LABEL_BYTES, MAX_RESULT_LABEL_BYTES, MAX_PATH_HITS)
        from backend.app.application.memory.querying.sag_query import SAGQueryStorage, COMMIT, search as core_search
        space = snapshot["spaces"].get(resolved_space_id) if resolved_space_id else None
        storage = SAGQueryStorage(self, actor, member, snapshot, descriptions, space, query.query, done, gaps, failures)
        storage.query_target_time = query.target_time
        storage.resume_paths = resume_paths
        core_result, core_config = {"items": [], "_timings": {}}, {}
        try:
            core_result, core_config = core_search(storage, expansion_enabled=self.expansion_enabled)
        except OperationCancelledError:
            raise
        except SerenitaError as exc:
            failures.append({"code": exc.code, "message": exc.message})
            storage.paths.clear()
            storage.native_items.clear()
            storage.visited.clear()
            storage.visited_entities.clear()
            storage.deferred.clear()
        # Native failures remain failures; no alternate home-grown retrieval.
        paths = storage.paths
        vector_hits = storage.vector_hits
        visited, visited_entities = storage.visited, storage.visited_entities
        examined = visited
        deferred = list(storage.deferred)
        stable = lambda key: (all_events[key]["record_sequence"], key)
        ranked = [item['event_id'] for item in core_result['items']]
        visited = set(ranked)
        limited_paths = storage.limited_paths
        native_items = storage.native_items
        confirmed_events = {row['event_id'] for row in snapshot['bindings'] if row['space_id'] == resolved_space_id
            and row['status'] and row['status']['state'] == 'confirmed'}
        missing_vectors = [key for key in descriptions if key not in confirmed_events]
        if missing_vectors:
            gaps.append({"code": "events_without_confirmed_vectors", "count": len(missing_vectors)})
        if storage.deferred:
            gaps.append({"code": "sag_retrieval_budget", "limit": 64})
        stage("sag_core", len(descriptions), len(ranked), core="sag", commit=COMMIT,
            timings=core_result['_timings'], model_calls=core_result.get('model_calls', []),
            state='empty_index' if core_result.get('empty_index') else ('failed' if failures and not ranked else 'completed'),
            visited_events=len(examined), visited_entities=len(visited_entities),
            seeds=sum(row['stage'] == 'seed' for row in core_result['items']))
        # Grouping is supplied from real relation records, never inferred by
        # string matching. A whole group moves together or is left unread.
        relation_result = self.relation_provider(actor, member, snapshot["record_cutoff"], ranked) if self.relation_provider else {"groups": [], "unread": [], "complete": False}
        groups = relation_result["groups"]
        if not relation_result["complete"] and self.relation_provider:
            gaps.append({"code": "relation_coverage_incomplete", "unread": relation_result["unread"]})
        if self.relation_provider is None:
            gaps.append({"code": "relation_coverage_unavailable", "detail": "本次检索未读取独立关系图，冲突与反证关系覆盖未知。"})
        selected, consumed, blocked_groups = [], set(), []
        # Merge intersecting groups so a shared item cannot silently split a
        # conflict component across pages.
        components = []
        for group in groups:
            combined = set(group)
            retained = []
            for previous in components:
                if combined.intersection(previous):
                    combined.update(previous)
                else:
                    retained.append(previous)
            components = [*retained, combined]
        grouping = {key: sorted((value for value in group if value in all_events), key=stable) for group in components for key in group if key in all_events}
        for key in ranked:
            group = [value for value in grouping.get(key, [key]) if value in all_events and value not in done]
            group = [value for value in group if value not in consumed]
            if any(value not in visited for value in group) or len(selected) + len(group) > 32:
                if group and group not in blocked_groups:
                    blocked_groups.append(group)
                continue
            selected.extend(group)
            consumed.update(group)
        stage("coarse_ranking", len(visited), len(selected), missing_vectors=len(missing_vectors))
        if blocked_groups:
            gaps.append({"code": "unread_groups", "groups": blocked_groups})
        unread = [key for key in ranked if key not in consumed and key not in done]
        unread.extend(deferred)
        unread.extend(value for group in blocked_groups for value in group)
        # A continuation runs the same native core over the remaining index
        # scope. Only actual recorded paths can be serialized into a cursor.
        unread.extend(key for key in storage.visited if key not in consumed)
        unread = list(dict.fromkeys(key for key in unread if key not in consumed and key not in done))
        fresh = repo.snapshot(actor, member, snapshot["record_cutoff"])
        final_times = repo.time_context(actor, member, {key: fresh["events"][key] for key in selected if key in fresh["events"]},
            snapshot["record_cutoff"])
        if final_times["unread"]:
            gaps.append({"code": "time_evaluation_incomplete", "unread": final_times["unread"]})
        candidates = []
        from backend.app.repositories.memory.reading.search_paths import authorized_chains
        verification = {}
        live_chains, path_truncated, permission_changed = authorized_chains(self.memory.repository, actor, member,
            snapshot['record_cutoff'], paths, fresh, query.query,
            diagnostic_ids={key for group in components for key in group}, verification=verification)
        if path_truncated or limited_paths:
            gaps.append({'code': 'connection_path_alternatives_budget', 'limit': 8})
        unavailable_groups = {key for group in components if any(value not in live_chains for value in group)
            for key in group}
        if set(selected).intersection(unavailable_groups):
            selected = [key for key in selected if key not in unavailable_groups]
            gaps.append({'code': 'relation_coverage_incomplete', 'unread': [{'reason': 'relation_group_unavailable'}]})
        ranking_hits, ranking_changed = ranking_evidence(self.memory.repository, actor, member, snapshot['record_cutoff'],
            {key: vector_hits.get(key, []) for key in selected}, fresh, query.query, verification=verification)
        permission_changed |= ranking_changed
        projection_lookup = hit_lookup(fresh, query.query)
        rich_by_key, returned_chains, label_bytes, omitted_metadata = {}, {}, 0, set()
        for key in selected:
            if key in returned_chains or key in omitted_metadata:
                continue
            group = [value for value in grouping.get(key, [key]) if value in selected]
            chains = {value: deepcopy(live_chains.get(value, [])) for value in group}
            rich = {value: project_hits(chains[value], fresh, lookup=projection_lookup, ranking_event=value, ranking_hits=ranking_hits[value]) for value in group}
            if any(encoded_size(hit) > MAX_SEED_LABEL_BYTES for value in rich.values() for hit in value.get('semantic', [])):
                chains = {value: [chain for chain in rows if not any('entity_hit' in step for step in chain)] for value, rows in chains.items()}
                rich = {value: project_hits(chains[value], fresh, lookup=projection_lookup, ranking_event=value, ranking_hits=ranking_hits[value]) for value in group}
                gaps.append({'code': 'retrieval_hit_budget', 'route': 'semantic', 'limit': MAX_SEED_LABEL_BYTES})
            for route in ('semantic', 'text', 'vector'):
                if label_bytes + sum(encoded_size(value) for value in rich.values()) <= MAX_RESULT_LABEL_BYTES:
                    break
                if route == 'semantic':
                    chains = {value: [chain for chain in rows if not any('entity_hit' in step for step in chain)] for value, rows in chains.items()}
                    rich = {value: project_hits(chains[value], fresh, lookup=projection_lookup, ranking_event=value, ranking_hits=ranking_hits[value]) for value in group}
                    gaps.append({'code': 'retrieval_hit_budget', 'route': route, 'limit': MAX_RESULT_LABEL_BYTES})
                    continue
                for paths_for_key in chains.values():
                    for chain in paths_for_key:
                        chain[0][route + '_hits'] = []
                        chain[0][route + '_rank'] = None
                if route == 'vector':
                    for value in group:
                        ranking_hits[value] = []
                chains = {value: [chain for chain in paths_for_key if chain[0]['text_hits'] or chain[0]['vector_hits']]
                    for value, paths_for_key in chains.items()}
                rich = {value: project_hits(chains[value], fresh, lookup=projection_lookup, ranking_event=value, ranking_hits=ranking_hits[value]) for value in group}
                gaps.append({'code': 'retrieval_hit_budget', 'route': route, 'limit': MAX_RESULT_LABEL_BYTES})
            if any(not chains[value] for value in group):
                omitted_metadata.update(group)
                unread.extend(value for value in group if value not in unread)
                continue
            label_bytes += sum(encoded_size(value) for value in rich.values())
            returned_chains.update(chains)
            rich_by_key.update(rich)
        for key in selected:
            if key not in fresh["events"]:
                continue
            actual_paths = []
            for chain in returned_chains.get(key, []):
                path = {name: value for name, value in chain[-1].items() if name != 'event_id'}
                if path not in actual_paths:
                    actual_paths.append(path)
            if not actual_paths:
                continue
            row = fresh["events"][key]
            try:
                repo.require(actor, member, "event", row["event_id"])
            except SerenitaError as exc:
                if exc.code == "MEMORY_OBJECT_UNAVAILABLE":
                    continue
                raise
            effective = final_times["events"].get(row["event_id"])
            if effective is None:
                continue
            matches_time = repo.matches_time(actor, member, effective, criteria)
            candidates.append({"event_id": key, "title": row["title"], "summary": row["summary"], "content": row["content"],
                "reference": {"object_type": "event", "object_id": row["event_id"]},
                "sag_score": native_items[key]['score'],
                'sag_basis': {'core': 'sag', 'commit': COMMIT, 'stage': native_items[key]['stage'],
                    'model_selected': native_items[key]['model_selected']},
                "vector_score": ranking_hits[key][0]['score'] if ranking_hits[key] else None,
                'ranking_vector_hits': ranking_hits[key], "source_paths": actual_paths,
                "source_chains": returned_chains[key], 'retrieval_hits': rich_by_key[key],
                "outside_target_time": bool(query.target_time is not None and final_times["complete"] and not matches_time),
                "effective_occurrence_time": effective["occurrence_time"], "occurrence_time_basis": effective.get("occurrence_time_basis", []),
                "time_evaluation_complete": final_times["complete"],
                "evidence_read": False})
        stage("return_permission_check", len(selected), len(candidates), excluded=len(selected) - len(candidates))
        continuation = None
        seen = sorted(done.union(row["event_id"] for row in candidates))
        unread = [key for key in unread if key in live_chains]
        cannot_resume = {key for group in blocked_groups if len(group) > 32 or any(value not in live_chains for value in group)
            for key in group}
        unread = [key for key in unread if key not in cannot_resume]
        if len(unread) > 5000 or len(seen) > 5000:
            gaps.append({"code": "continuation_budget_exceeded", "detail": "请缩小查询范围后继续。"})
        elif unread:
            from backend.app.application.memory.querying.search_continuation import encode
            # Retain every deferred node and its exact original seed. Optional
            # alternate chains share the same finite cursor metadata budget.
            maximum_paths = max(len(live_chains[key]) for key in unread)
            for path_count in range(maximum_paths, 0, -1):
                try:
                    continuation = encode(scope, seen, unread,
                        {key: live_chains[key][:path_count] for key in unread})
                    if path_count < maximum_paths:
                        gaps.append({'code': 'connection_path_alternatives_budget', 'limit': path_count,
                            'scope': 'continuation'})
                    break
                except SerenitaError as exc:
                    if exc.code != 'MEMORY_CONTINUATION_BUDGET':
                        raise
            if continuation is None:
                gaps.append({'code': 'continuation_budget_exceeded', 'detail': '请缩小查询范围后继续。'})
        if permission_changed:
            # Earlier diagnostics may contain identities from the old access
            # snapshot. Keep the actual coverage failures without disclosing
            # their now-unavailable endpoints, references or bindings.
            gaps = [{'code': row['code'], 'detail': '读取期间来源权限或连接依据发生变化，受限内容未返回。'} for row in gaps]
            if not gaps:
                gaps.append({'code': 'source_access_changed', 'detail': '读取期间来源权限发生变化，覆盖范围不完整。'})
            gaps.append({'code': 'retrieval_evidence_changed', 'detail': '原检索的部分命中或连接依据已不可用，已移除相关路径。'})
            failures = [{'code': row['code'], 'message': '读取期间来源权限发生变化，相关内容不可用。'} for row in failures]
        return {"query": query.query, "member_id": member, "account_id": snapshot["account_id"], "space_id": resolved_space_id,
            "record_cutoff": snapshot["record_cutoff"], "target_time": scope["target_time"], "candidates": candidates, "budgets": dict(BUDGETS), "stages": stages,
            "retrieval_controls": {"expansion_enabled": self.expansion_enabled, "sag_config": core_config},
            'retrieval_metadata_budget': {'text_hits_per_seed': MAX_TEXT_HITS, 'text_label_bytes_per_seed': MAX_SEED_LABEL_BYTES,
                'result_label_bytes': MAX_RESULT_LABEL_BYTES, 'path_hits': MAX_PATH_HITS},
            "gaps": gaps, "failures": failures, "coverage": {"returned": len(candidates), "unread": len(unread), "complete": not unread and not gaps and not failures},
            "continuation": continuation}

