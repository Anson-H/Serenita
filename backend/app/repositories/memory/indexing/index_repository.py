"""SAG metadata validation and append-only LanceDB access.

SQLite confirmation is the authority. A physical Lance row alone is never an
index entry. Committed vectors are immutable. Only unpublished rows belonging
to a failed staging publication may be discarded by its publication journal.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
import math
import re
import unicodedata









def validate_index_append(repo, connection, access, batch, *, extraction_mentions=None):
    """Called inside the root repository transaction after insertion, before commit."""
    for item in batch.event_entities:
        entity = repo._require(connection, access, "entity", item.entity_id)
        event = repo._require(connection, access, "event", item.event_id)
        from backend.app.repositories.memory.facts.entity_roles import validate_event_entity
        validate_event_entity(repo, connection, access, event, entity, item.description,
            (extraction_mentions or {}).get(item.event_id))
    for item in [*batch.entities, *batch.entity_names]:
        event = repo._require(connection, access, "event", item.event_id)
        from backend.app.repositories.memory.sources.evidence import change_references,read_change,change_source
        changes=[read_change(repo,access,ref,connection) for ref in change_references(repo,connection,access,event)]
        evidence_text = [event["content"],*(change_source(change)['content_text'] for change in changes)]
        normalize = lambda value: " ".join(unicodedata.normalize("NFKC", value).casefold().split())
        name = getattr(item, "canonical_name", None) or item.name
        native_entity = any(mention['entity_id'] == item.entity_id and
            name.strip() in [value.strip() for value in (mention['name'], *mention['aliases'])]
            for mention in (extraction_mentions or {}).get(item.event_id, []))
        # SAG resolves pronouns and complete names using context. The native
        # association above verifies the actual extracted name and role; a
        # substring test cannot validate that semantic extraction.
        if not native_entity and not any(normalize(name) in normalize(text) for text in evidence_text):
            fail("MEMORY_ENTITY_NAME_UNPROVEN", "实体名称或别名必须在实际依据 Event 或来源内容中出现。")
        if getattr(item, "formal_resource_id", None) is not None:
            matched = any(change['resource_type']==item.formal_resource_type and change['resource_id']==item.formal_resource_id for change in changes)
            if not matched:
                fail("MEMORY_ENTITY_FORMAL_IDENTITY_UNPROVEN", "正式业务身份必须由依据 Event 的实际业务来源证明。")
            duplicate = connection.execute('SELECT 1 FROM entities WHERE account_id=? AND member_id=? '
                'AND formal_resource_type=? AND formal_resource_id=? AND entity_id<>? LIMIT 1',
                (access.account_id, access.member_id, item.formal_resource_type, item.formal_resource_id, item.entity_id)).fetchone()
            if duplicate is not None:
                fail('MEMORY_ENTITY_FORMAL_IDENTITY_CONFLICT', '该正式业务对象已有实体身份，须读取后复用，不能创建重复身份。')
        if not connection.execute("SELECT 1 FROM event_entities WHERE entity_id=? AND event_id=? AND account_id=? AND member_id=? LIMIT 1", (item.entity_id, item.event_id, access.account_id, access.member_id)).fetchone():
            fail("MEMORY_ENTITY_BASIS", "实体名称依据必须对应已保存的事件与实体关联。")
    for item in batch.vector_bindings:
        repo._require(connection, access, "event", item.event_id)
        repo._require(connection, access, "vector_space", item.space_id)
        if not any(status.binding_id == item.binding_id and status.previous_status_id is None and status.state == "pending" for status in batch.vector_statuses):
            fail("MEMORY_VECTOR_PENDING_REQUIRED", "新向量绑定必须同时追加初始待处理状态。")
    for request in batch.vector_request_parameters:
        repo._require(connection, access, "event", request.event_id)
        attempt = repo._require(connection, access, "processing_attempt", request.attempt_id)
        if attempt["task_kind"] != "vector_index" or request.attempt_id not in {row.attempt_id for row in batch.attempts}:
            fail("MEMORY_VECTOR_REQUEST_ATTEMPT", "向量请求参数必须随其新的向量计算尝试共同提交。")
    transitions = {"pending": {"confirmed", "failed"}, "failed": {"pending"}, "confirmed": set()}
    vectors = None
    for item in batch.vector_statuses:
        binding = repo._require(connection, access, "vector_binding", item.binding_id)
        binding["text_hash"] = repo._require(connection, access, "event", binding["event_id"])["text_hash"]
        if item.previous_status_id is None:
            if item.state != "pending":
                fail("MEMORY_VECTOR_STATUS_TRANSITION", "向量绑定初始状态必须为待处理。")
        else:
            previous = connection.execute("SELECT state FROM event_vector_statuses WHERE binding_id=? AND status_id=? AND account_id=? AND member_id=?", (item.binding_id, item.previous_status_id, access.account_id, access.member_id)).fetchone()
            if previous is None or item.state not in transitions[previous[0]]:
                fail("MEMORY_VECTOR_STATUS_TRANSITION", "向量状态只能沿允许的线性历史追加。")
        if item.state == "confirmed":
            space = repo._require(connection, access, "vector_space", binding["space_id"])
            vectors = vectors or LanceVectors(repo.paths)
            vectors.confirm(access.account_id, access.member_id, binding, space, item.vector_hash)


def entity_terms(value):
    normalized = " ".join(unicodedata.normalize("NFKC", value).casefold().split())
    result = []
    for token in re.findall(r"[\u3400-\u4dbf\u4e00-\u9fff]+|[^\W_]+", normalized, re.UNICODE):
        if all("\u3400" <= ch <= "\u4dbf" or "\u4e00" <= ch <= "\u9fff" for ch in token):
            result.extend(token[i:i + 2] for i in range(len(token) - 1)) if len(token) > 1 else result.append(token)
        else:
            result.append(token)
    return result


def bm25(query, corpus):
    """Deterministic scores over the already-authorized entity-name corpus."""
    terms = set(entity_terms(query))
    documents = {key: Counter(entity_terms(text)) for key, text in corpus.items()}
    if not documents or not terms:
        return {}
    sizes = {key: sum(counts.values()) for key, counts in documents.items()}
    average = sum(sizes.values()) / len(sizes) or 1
    frequency = {term: sum(term in counts for counts in documents.values()) for term in terms}
    scores = {}
    for key, counts in documents.items():
        score = 0.0
        for term in terms:
            count = counts[term]
            if count:
                idf = math.log(1 + (len(documents) - frequency[term] + .5) / (frequency[term] + .5))
                score += idf * count * 2.2 / (count + 1.2 * (.25 + .75 * sizes[key] / average))
        if score > 0:
            scores[key] = score
    return scores


class MemoryIndexRepository:
    def __init__(self, memory_repository):
        self.memory = memory_repository
        self.paths = memory_repository.paths
        self.vectors = LanceVectors(self.paths)

    def snapshot(self, actor, member, record_cutoff=None):
        repo = self.memory
        with repo._transaction(actor, member) as (access, connection):
            cutoff = repo._cutoff(connection, access, record_cutoff)
            from backend.app.repositories.memory.reading.prepared_reads import prepared_reads
            from backend.app.repositories.memory.reading.read_cache import access_key
            prepared = prepared_reads(repo, access)
            key = (*access_key(access), cutoff)
            if prepared is not None and key in prepared.index_snapshots:
                return self.authorize_snapshot(actor, member, prepared.index_snapshots[key])
            result = {"account_id": access.account_id, "member_id": member, "record_cutoff": cutoff,
                      "events": {}, "entities": {}, "names": [], "links": [], "spaces": {}, "bindings": [], "excluded": 0}
            if connection is None:
                return result
            tables = (("events", "event", "event_id", "events"),
                      ("entities", "entity", "entity_id", "entities"), ("entity_names", "entity_name", "name_id", "names"),
                      ("vector_spaces", "vector_space", "space_id", "spaces"), ("event_vectors", "vector_binding", "binding_id", "bindings"))
            for table, kind, identity, collection in tables:
                rows = connection.execute(f"SELECT o.*,c.sequence AS record_sequence, c.submitted_at FROM {table} o JOIN commits c USING(commit_id) WHERE o.account_id=? AND o.member_id=? AND c.sequence<=? ORDER BY c.sequence,o.{identity}", (access.account_id, member, cutoff)).fetchall()
                for raw in rows:
                    row = {**repo._decode(dict(raw)), "object_type": kind}
                    if not repo._visible(connection, access, row):
                        result["excluded"] += 1
                        continue
                    if kind == "vector_binding":
                        row["text_hash"] = result["events"][row["event_id"]]["text_hash"]
                    if isinstance(result[collection], dict):
                        result[collection][row[identity]] = row
                    else:
                        result[collection].append(row)
            for raw in connection.execute(
                    "SELECT o.*,c.submitted_at FROM event_entities o JOIN commits c USING(commit_id) "
                    "WHERE o.account_id=? AND o.member_id=? AND c.sequence<=?",
                    (access.account_id, member, cutoff)):
                row = dict(raw)
                if row["event_id"] in result["events"] and row["entity_id"] in result["entities"]:
                    result["links"].append(row)
            visible_bindings = {row["binding_id"] for row in result["bindings"]}
            statuses = {}
            if visible_bindings:
                for status in connection.execute("SELECT s.*,c.sequence,c.submitted_at FROM event_vector_statuses s JOIN commits c USING(commit_id) WHERE s.account_id=? AND s.member_id=? AND c.sequence<=? AND NOT EXISTS (SELECT 1 FROM event_vector_statuses n JOIN commits nc ON nc.commit_id=n.commit_id WHERE n.binding_id=s.binding_id AND n.previous_status_id=s.status_id AND nc.sequence<=?)", (access.account_id, member, cutoff, cutoff)):
                    if status["binding_id"] in visible_bindings:
                        statuses[status["binding_id"]] = dict(status)
            for binding in result["bindings"]:
                status = statuses.get(binding["binding_id"])
                binding["status"] = status
                binding["vector_hash"] = status["vector_hash"] if status else None
            if prepared is not None:
                # Keep only the latest requested cutoff within this execution.
                prepared.index_snapshots.clear()
                prepared.index_snapshots[key] = deepcopy(result)
            return result

    def authorize_snapshot(self, actor, member, snapshot, *, event_ids=None, entity_ids=None):
        """Recheck live access while reusing fixed content at the query cutoff."""
        repo = self.memory
        with repo._transaction(actor, member) as (access, db):
            if snapshot['account_id'] != access.account_id or snapshot['member_id'] != member:
                fail('MEMORY_SEARCH_SCOPE_MISMATCH', '索引输入与当前成员不同。', kind='forbidden')
            events = set(snapshot['events']) if event_ids is None else set(event_ids)
            if entity_ids is not None:
                events.intersection_update(row['event_id'] for row in snapshot['links'] if row['entity_id'] in entity_ids)
            result = {**snapshot, 'events': {key: dict(row) for key, row in snapshot['events'].items()
                if key in events and repo._visible(db, access, row)}}
            result['links'] = [dict(row) for row in snapshot['links'] if row['event_id'] in result['events']]
            entities = {row['entity_id'] for row in result['links']}
            if entity_ids is not None:
                entities.intersection_update(entity_ids)
            result['entities'] = {key: dict(row) for key, row in snapshot['entities'].items()
                if key in entities and repo._visible(db, access, row)}
            result['links'] = [row for row in result['links'] if row['entity_id'] in result['entities']]
            result['names'] = [dict(row) for row in snapshot['names']
                if row['entity_id'] in result['entities'] and repo._visible(db, access, row)]
            result['spaces'] = {key: dict(row) for key, row in snapshot['spaces'].items() if repo._visible(db, access, row)}
            result['bindings'] = [dict(row) for row in snapshot['bindings']
                if row['event_id'] in result['events'] and row['space_id'] in result['spaces'] and repo._visible(db, access, row)]
            return result

    def delivery_context(self, actor, member, event_id):
        """Recover only this event's saved entity targets after interruption."""
        repo = self.memory
        with repo._transaction(actor, member) as (access, db):
            repo._require(db, access, 'event', event_id)
            links, names = [], []
            for raw in db.execute('SELECT event_id,entity_id FROM event_entities '
                    'WHERE event_id=? AND account_id=? AND member_id=?',
                    (event_id, access.account_id, member)):
                repo._require(db, access, 'entity', raw['entity_id'])
                links.append(dict(raw))
            for raw in db.execute('SELECT event_id,entity_id,name_id FROM entity_names '
                    'WHERE event_id=? AND account_id=? AND member_id=?',
                    (event_id, access.account_id, member)):
                repo._require(db, access, 'entity_name', raw['entity_id'], item_id=raw['name_id'])
                names.append(dict(raw))
            return {'links': links, 'names': names}

    def binding_snapshot(self, actor, member, binding_id, space_id, record_cutoff=None):
        """Read one binding, its actual status head and the requested space.

        The committed cutoff and live source checks share one read transaction.
        No unrelated descriptions, entities, bindings or vectors are loaded.
        """
        repo = self.memory
        with repo._transaction(actor, member) as (access, connection):
            cutoff = repo._cutoff(connection, access, record_cutoff)
            result = {"account_id": access.account_id, "member_id": member,
                      "record_cutoff": cutoff, "binding": None, "space": None}
            if connection is None:
                return result
            for table, kind, key, identity, field in (
                ("event_vectors", "vector_binding", "binding_id", binding_id, "binding"),
                ("vector_spaces", "vector_space", "space_id", space_id, "space"),
            ):
                raw = connection.execute(
                    f"SELECT o.*,c.sequence AS record_sequence, c.submitted_at FROM {table} o "
                    f"JOIN commits c USING(commit_id) WHERE o.{key}=? "
                    "AND o.account_id=? AND o.member_id=? AND c.sequence<=?",
                    (identity, access.account_id, member, cutoff)).fetchone()
                row = {**repo._decode(dict(raw)), "object_type": kind} if raw else None
                if repo._visible(connection, access, row):
                    result[field] = row
            binding = result["binding"]
            if binding is not None:
                binding["text_hash"] = repo._require(connection, access, "event", binding["event_id"], cutoff=cutoff)["text_hash"]
                raw = connection.execute(
                    "SELECT s.*,c.sequence,c.submitted_at FROM event_vector_statuses s "
                    "JOIN commits c USING(commit_id) WHERE s.binding_id=? "
                    "AND s.account_id=? AND s.member_id=? AND c.sequence<=? "
                    "AND NOT EXISTS (SELECT 1 FROM event_vector_statuses n "
                    "JOIN commits nc ON nc.commit_id=n.commit_id "
                    "WHERE n.binding_id=s.binding_id AND n.previous_status_id=s.status_id AND nc.sequence<=?)",
                    (binding_id, access.account_id, member, cutoff, cutoff)).fetchone()
                binding["status"] = dict(raw) if raw else None
                binding["vector_hash"] = raw["vector_hash"] if raw else None
            return result

    def require(self, actor, member, kind, identity, *, item_id=None):
        with self.memory._transaction(actor, member) as (access, connection):
            return self.memory._require(connection, access, kind, identity, item_id=item_id)

    def time_context(self, actor, member, descriptions, cutoff):
        from backend.app.domain.memory.statistics import effective_occurrence_times
        from backend.app.repositories.memory.facts.relations import event_relations_at
        repo = self.memory
        with repo._transaction(actor, member) as (access, connection):
            graph = event_relations_at(repo, connection, access, cutoff, limit=500)
            applicable = graph["pairs"]
            ids = {row["event_id"] for row in descriptions.values()}
            # Time correction chains may point to Events without an index yet.
            ids.update(identity for pair in applicable for identity in (pair["relation"]["from_event_id"], pair["relation"]["to_event_id"]))
            events = []
            for identity in ids:
                row = repo._record(connection, access, "event", identity, cutoff=cutoff)
                if repo._visible(connection, access, row):
                    events.append(row)
            effective, time_gaps = effective_occurrence_times(events, applicable)
            return {"events": {row["event_id"]: row for row in effective},
                "unread": [*graph["unread"], *time_gaps],
                "complete": graph["complete"] and not time_gaps}


    def filter_event_times(self, actor, member, descriptions, times, criteria):
        with self.memory._transaction(actor, member) as (access, db):
            return {key: row for key, row in descriptions.items() if row['event_id'] in times['events']
                and (not times['complete'] or self.memory._matches(db, access, times['events'][row['event_id']], criteria))}

    def matches_time(self, actor, member, event, criteria):
        with self.memory._transaction(actor, member) as (access, db):
            return self.memory._matches(db, access, event, criteria)

from backend.app.domain.memory.vectors import fail

from backend.app.repositories.memory.indexing.vector_store import LanceVectors
