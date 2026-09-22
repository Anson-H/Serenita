"""SAG storage uses the same immutable event IDs as memory and its graph."""
from backend.app.domain.memory.event_text import event_text
from collections import defaultdict

from backend.app.repositories.memory.indexing.index_repository import bm25
from backend.app.domain.memory.vectors import fail
from backend.app.repositories.memory.indexing.semantic_index_repository import MemorySemanticIndexRepository


class SAGStorage:
    def __init__(self, index, actor, member, *, space_id, record_cutoff=None, event_ids=None):
        self.index, self.repo = index, index.repository
        self.semantic = MemorySemanticIndexRepository(self.repo.memory)
        self.actor, self.member = actor, member
        snapshot = self.repo.snapshot(actor, member, record_cutoff)
        self._fixed_snapshot = snapshot
        self.cutoff, self.space_id = snapshot['record_cutoff'], space_id
        self.allowed = set(snapshot['events']) if event_ids is None else set(event_ids).intersection(snapshot['events'])
        self.seen_events, self.seen_entities = set(), set()
        self.deferred_events, self.deferred_entities = set(), set()
        self._evidence, self._failures = [], []
        self.query_vector = None
        self.query_probes = set()

    def fresh(self, scope=None, *, event_ids=None, entity_ids=None):
        self.index.check_running()
        if scope is not None and scope != [self.member]:
            fail('MEMORY_SEARCH_SCOPE_MISMATCH', 'SAG 查询与当前成员不一致。')
        snapshot = self.repo.authorize_snapshot(self.actor, self.member, self._fixed_snapshot,
            event_ids=self.allowed if event_ids is None else self.allowed.intersection(event_ids), entity_ids=entity_ids)
        snapshot['events'] = {key: row for key, row in snapshot['events'].items() if key in self.allowed}
        snapshot['links'] = [row for row in snapshot['links'] if row['event_id'] in snapshot['events']]
        # Entity recall must have an authorized path to the requested event set.
        entities = {row['entity_id'] for row in snapshot['links']}
        snapshot['entities'] = {key: row for key, row in snapshot['entities'].items() if key in entities}
        snapshot['names'] = [row for row in snapshot['names'] if row['entity_id'] in entities]
        return snapshot

    def space(self, snapshot):
        space = snapshot['spaces'].get(self.space_id)
        if space is None:
            fail('MEMORY_VECTOR_SPACE_UNAVAILABLE', 'SAG 检索需要当前可读取的已保存向量空间。')
        return space

    def admit(self, ids, *, entities=False):
        seen = self.seen_entities if entities else self.seen_events
        deferred = self.deferred_entities if entities else self.deferred_events
        limit = 32 if entities else 64
        accepted = []
        for identity in dict.fromkeys(ids):
            if identity not in seen and len(seen) >= limit:
                deferred.add(identity)
            else:
                seen.add(identity)
                accepted.append(identity)
        return accepted

    def remember(self, rows, kind):
        for row in rows:
            hit = {key: row[key] for key in ('binding_id', 'vector_id', 'space_id', 'text_hash', 'vector_hash', 'event_id')}
            hit.update(index_kind=kind, status_id=row['status']['status_id'], cosine_score=row['score'], sag_score=sag_score(row['score']))
            if kind != 'event':
                hit.update({key: row[key] for key in ('entity_id', 'name_id')})
            if hit not in self._evidence:
                self._evidence.append(hit)

    def evidence(self, *, snapshot=None):
        """Project stored hit identities only after rechecking live access."""
        fresh = self.fresh() if snapshot is None else snapshot
        semantic = self.semantic.snapshot(self.actor, self.member, self.cutoff,
            binding_ids=[row['binding_id'] for row in [*self._evidence, *self._failures] if row.get('index_kind') != 'event'])
        visible = {row['binding_id'] for row in fresh['bindings'] if row['event_id'] in fresh['events']}
        visible.update(row['binding_id'] for row in semantic['bindings'] if row['entity_id'] in fresh['entities']
            and (row['index_kind'] == 'entity_name' or row['event_id'] in fresh['events']))
        return {'vector_hits': [dict(row) for row in self._evidence if row['binding_id'] in visible],
            'query_probes': sorted(self.query_probes.intersection(fresh['events'])),
            'failures': [dict(row) for row in self._failures if row['binding_id'] in visible],
            'deferred_event_ids': sorted(self.deferred_events.intersection(fresh['events'])),
            'deferred_entity_ids': sorted(self.deferred_entities.intersection(fresh['entities']))}

    async def get_processor(self):
        self.index.check_running()
        return self

    async def generate_embedding(self, text):
        snapshot = self.fresh()
        vector = self.index.vector_models.embed(snapshot['account_id'], self.member, self.space(snapshot), text)
        self.fresh()
        return vector

    async def generate_embeddings_batch(self, texts):
        snapshot = self.fresh()
        return self.index.vector_models.embed_many(snapshot['account_id'], self.member, self.space(snapshot), texts, guard=self.fresh)

    async def search_events_by_vector(self, *, query_vector, k, source_config_ids=None, event_ids=None):
        self.query_vector = query_vector
        fresh = self.fresh(source_config_ids, event_ids=event_ids)
        allowed = set(fresh['events'])
        if event_ids is not None:
            allowed.intersection_update(event_ids)
        bindings = [row for row in fresh['bindings'] if row['event_id'] in allowed and row['space_id'] == self.space_id
            and row['status'] and row['status']['state'] == 'confirmed']
        rows, failures = self.repo.vectors.search(fresh['account_id'], self.member, self.space(fresh), query_vector, bindings)
        self._failures.extend(failures)
        live = self.fresh(source_config_ids, event_ids={row['event_id'] for row in rows})
        visible = {row['binding_id'] for row in live['bindings'] if row['event_id'] in live['events']}
        best = {}
        for row in sorted(rows, key=lambda row: (-row['score'], row['binding_id'])):
            if row['binding_id'] in visible:
                best.setdefault(row['event_id'], row)
        ids = list(best)
        self.deferred_events.update(ids[k:])
        if event_ids is None:
            probes = ids[k:k + 64]
            self.query_probes.update(probes)
            self.remember([best[key] for key in probes], 'event')
        accepted = self.admit(ids[:k])
        self.remember([best[key] for key in accepted], 'event')
        links = defaultdict(set)
        for link in live['links']:
            links[link['event_id']].add(link['entity_id'])
        return [{'event_id': key, 'entity_ids': sorted(links[key]), '_score': sag_score(best[key]['score'])} for key in accepted]

    async def coarse_rank_events(self, event_ids, source_config_ids, *, max_events, query_vector):
        if not event_ids:
            return []
        rows = await self.search_events_by_vector(query_vector=query_vector, k=max_events,
            source_config_ids=source_config_ids, event_ids=event_ids)
        return [{'event_id': row['event_id'], 'score': row['_score']} for row in rows]

    def semantic_search(self, vector, kind, *, scope, entity_ids=None, event_ids=None):
        fresh = self.fresh(scope, event_ids=event_ids, entity_ids=entity_ids)
        entities = set(fresh['entities'])
        if entity_ids is not None:
            entities.intersection_update(entity_ids)
        rows, failures = self.semantic.search(self.actor, self.member, self.space(fresh), vector,
            index_kind=kind, record_cutoff=self.cutoff, entity_ids=entities, event_ids=event_ids)
        self._failures.extend(failures)
        live = self.fresh(scope, entity_ids={row['entity_id'] for row in rows})
        return sorted((row for row in rows if row['entity_id'] in live['entities']
            and (row['index_kind'] == 'entity_name' or row['event_id'] in live['events'])),
            key=lambda row: (-row['score'], row['binding_id']))

    async def retrieve_entity_candidates(self, query_entities, source_config_ids, *, entity_top_k,
                                         key_similarity_threshold, allowed_entity_ids=None):
        self.fresh(source_config_ids)
        selected = {}
        for vector in await self.generate_embeddings_batch(query_entities):
            rows = self.semantic_search(vector, 'entity_name', scope=source_config_ids, entity_ids=allowed_entity_ids)
            best = {}
            for row in rows:
                best.setdefault(row['entity_id'], row)
            for key, row in list(best.items())[:entity_top_k]:
                if sag_score(row['score']) >= key_similarity_threshold:
                    selected.setdefault(key, row)
        live = self.fresh(source_config_ids)
        ids = self.admit([key for key in selected if key in live['entities']], entities=True)
        self.remember([selected[key] for key in ids], 'entity_name')
        return ids, [selected[key]['name'] for key in ids], [sag_score(selected[key]['score']) for key in ids]

    async def search_event_entities_by_vector(self, *, query_vector, k, event_ids, source_config_ids):
        fresh = self.fresh(source_config_ids)
        ids = set(event_ids).intersection(fresh['events'])
        rows = self.semantic_search(query_vector, 'entity_role', scope=source_config_ids, event_ids=ids)
        best = {}
        for row in rows:
            best.setdefault((row['event_id'], row['entity_id']), row)
        selected = list(best.values())[:k]
        self.remember(selected, 'entity_role')
        return [{'event_id': row['event_id'], 'entity_id': row['entity_id'], '_score': sag_score(row['score'])} for row in selected]

    async def retrieve_entity_event_pairs(self, entity_ids, source_config_ids, *, max_events_per_entity, exclude_event_ids=None):
        fresh = self.fresh(source_config_ids)
        ids = self.admit([key for key in entity_ids if key in fresh['entities']], entities=True)
        excluded, pairs, counts = set(exclude_event_ids or ()), {}, defaultdict(int)
        for link in sorted(fresh['links'], key=lambda row: (fresh['events'][row['event_id']]['record_sequence'], row['event_id'], row['entity_id'])):
            event, entity = link['event_id'], link['entity_id']
            if entity not in ids or event in excluded:
                continue
            if counts[entity] >= max_events_per_entity:
                self.deferred_events.add(event)
                continue
            if not self.admit([event]):
                continue
            counts[entity] += 1
            pairs.setdefault(event, []).append(entity)
        return pairs, list(pairs)

    async def search_entities_by_text(self, query, source_config_ids, size, allowed_entity_ids=None):
        fresh = self.fresh(source_config_ids)
        allowed = set(fresh['entities'])
        if allowed_entity_ids is not None:
            allowed.intersection_update(allowed_entity_ids)
        names = defaultdict(list)
        for row in fresh['names']:
            names[row['entity_id']].append(row['name'])
        scores = bm25(query, {key: ' '.join([fresh['entities'][key]['canonical_name'], *names[key]]) for key in allowed})
        ranking = sorted((key for key in scores if scores[key] > 0), key=lambda key: (-scores[key], key))
        self.deferred_entities.update(ranking[size:])
        return [{'entity_id': key, 'name': fresh['entities'][key]['canonical_name'], '_score': scores[key]}
            for key in self.admit(ranking[:size], entities=True)]

    async def get_events_by_ids(self, event_ids, source_includes):
        fresh = self.fresh(event_ids=event_ids)
        links = defaultdict(set)
        for row in fresh['links']:
            links[row['event_id']].add(row['entity_id'])
        return [{'event_id': key, 'source_event_id': fresh['events'][key]['event_id'],
            'content': event_text(fresh['events'][key]), 'entity_ids': sorted(links[key])}
            for key in self.admit([key for key in event_ids if key in fresh['events']])]

    async def get_entities_by_ids(self, entity_ids):
        fresh = self.fresh(entity_ids=entity_ids)
        return [{'entity_id': key, 'name': fresh['entities'][key]['canonical_name']}
            for key in self.admit([key for key in entity_ids if key in fresh['entities']], entities=True)]

from backend.app.domain.memory.scores import sag_score
