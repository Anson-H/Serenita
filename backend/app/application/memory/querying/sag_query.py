"""SAG retrieval composed with immutable upper-layer evidence and continuation."""
from collections import defaultdict

from backend.app.application.memory.sag.core import run_core
from backend.app.application.memory.querying.sag_runtime import HostSAGRuntime, search_sag
from backend.app.repositories.memory.reading.sag_paths import paths_from_sag
from backend.app.repositories.memory.reading.search_paths import authorized_chains
from backend.app.core.cancellation import OperationCancelledError
from backend.app.core.errors import SerenitaError
from backend.app.providers.errors import ProviderChatCompletionError
from zleap.sag.config import SAGConfig
from zleap.sag.contracts import SAGSearchState
from zleap.sag.expand import SAGExpandStage
from zleap.sag.routes import SAGRouteTracker
from zleap.sag.timing import SAGTimingService


COMMIT = '942f498fb20001ade7492756a9002b5f6ad750d8'


class SAGQueryStorage:
    def __init__(self, service, actor, member, snapshot, descriptions, space, query, done, gaps, failures):
        self.service, self.actor, self.member, self.snapshot = service, actor, member, snapshot
        self.query, self.done, self.gaps, self.failures = query, done, gaps, failures
        self.allowed = set(descriptions)
        self.runtime = HostSAGRuntime(service, actor, member, space_id=space['space_id'] if space else None,
            record_cutoff=snapshot['record_cutoff'], event_ids=self.allowed.difference(done))
        self.visited, self.visited_entities = self.runtime.seen_events, self.runtime.seen_entities
        self.deferred, self.depths = set(), {}
        self.paths, self.vector_hits, self.vector_scores, self.native_items = defaultdict(list), {}, {}, {}
        self.resume_paths, self.query_target_time, self.limited_paths = {}, None, False
        self.blocked_resume = set()

    def fresh(self):
        self.service.check_running()
        result = self.service.repository.snapshot(self.actor, self.member, self.snapshot['record_cutoff'])
        result['events'] = {key: row for key, row in result['events'].items() if key in self.allowed and key not in self.blocked_resume}
        result['links'] = [row for row in result['links'] if row['event_id'] in result['events']]
        return result

    def admit(self, ids):
        accepted = self.runtime.admit([key for key in ids if key not in self.done and key not in self.blocked_resume])
        self.deferred.update(self.runtime.deferred_events)
        return accepted

    def add_paths(self, paths):
        for identity, steps in paths.items():
            for path in steps:
                if path in self.paths[identity]:
                    continue
                if len(self.paths[identity]) < 8:
                    self.paths[identity].append(path)
                    self.depths[identity] = min(self.depths.get(identity, 3), path.get('hop', 0))
                else:
                    self.limited_paths = True

    def add_item(self, identity, *, stage, score=None, model_selected=False):
        if identity in self.native_items or not self.admit([identity]):
            return
        # A bounded I/O probe is only a continuation locator. It cannot turn a
        # two-hop event into a direct seed when another route later reaches it.
        self.paths[identity] = [path for path in self.paths[identity] if path['route'] != 'query_probe']
        if self.paths[identity]:
            self.depths[identity] = min(path.get('hop', 0) for path in self.paths[identity])
        else:
            self.depths.pop(identity, None)
        self.native_items[identity] = {'event_id': identity, 'score': score, 'stage': stage,
            'model_selected': model_selected}

    def remember(self, result):
        paths, vectors, limited = paths_from_sag(result)
        self.add_paths(paths)
        self.limited_paths |= limited
        for identity, hit in vectors.items():
            self.vector_hits[identity], self.vector_scores[identity] = [hit], hit['score']


def _resume(storage, *, prepare=False):
    paths = defaultdict(list)
    for chains in storage.resume_paths.values():
        for chain in chains:
            for step in chain:
                path = {key: value for key, value in step.items() if key != 'event_id'}
                if path not in paths[step['event_id']]:
                    paths[step['event_id']].append(path)
    if not paths:
        return
    live, limited, changed = authorized_chains(storage.service.memory.repository, storage.actor, storage.member,
        storage.snapshot['record_cutoff'], paths, storage.fresh(), storage.query)
    if changed:
        if not any(row['code'] == 'retrieval_evidence_changed' for row in storage.gaps):
            storage.gaps.append({'code': 'retrieval_evidence_changed', 'detail': '部分继续路径的原始依据已不可读取。'})
    if prepare:
        storage.blocked_resume.update(set(storage.resume_paths).difference(live))
        storage.runtime.allowed.difference_update(storage.blocked_resume)
        return
    storage.limited_paths |= limited
    for identity in storage.resume_paths:
        probes_only = all(len(chain) == 1 and chain[0]['route'] == 'query_probe' for chain in live.get(identity, []))
        if probes_only and identity in storage.native_items:
            continue
        for chain in live.get(identity, []):
            storage.add_paths({step['event_id']: [{key: value for key, value in step.items() if key != 'event_id'}]
                for step in chain})
        if identity in live and probes_only:
            storage.deferred.add(identity)
        elif identity in live:
            storage.add_item(identity, stage='evidence_continuation')


def _expand_entities(storage, frontier, hop):
    """Run the pinned role/event filters after an upper-layer connection."""
    runtime = storage.runtime
    if not frontier or runtime.query_vector is None:
        return
    config = SAGConfig(sag_expand={'max_hops': 1, 'entities_per_hop': 32, 'max_events_per_hop': 64})
    stage = SAGExpandStage(runtime, SAGTimingService(runtime, ctx_var_name='sag_upper_expansion'))
    async def expand():
        mapping, entities = await stage._new_entities_from_event_ids(frontier, [storage.member], 32,
            set(runtime.seen_entities), runtime.query_vector, config)
        pairs, ids, scores = await stage._events_from_new_entities(entities, storage.query, [storage.member],
            runtime.query_vector, config, SAGSearchState(seen_event_ids=set(storage.visited)), 64)
        routes = SAGRouteTracker.new_route_index(storage.query)
        SAGRouteTracker.record_relation(route_index=routes, pairs_mapping=mapping, event_scores={},
            method='seed_event_to_key', relation='SAG event->key', hop=hop + 1, from_hop=hop, to_hop=hop + 1,
            key_is_event=False, from_is_event=True, stats_key='event_key_paths')
        SAGRouteTracker.record_relation(route_index=routes, pairs_mapping=pairs, event_scores=scores,
            method='expand_key_to_event', relation='SAG key->event', hop=hop + 1, from_hop=hop + 1, to_hop=hop + 1,
            key_is_event=True, from_is_event=False, stats_key='entity_event_paths')
        return ids, scores, routes
    ids, scores, routes = run_core(expand())
    storage.remember({'query_event_ids': [], 'route_index': routes, 'vector_evidence': runtime.evidence()})
    for identity in ids:
        storage.add_item(identity, stage='entity_expansion', score=scores[identity])


def _extend_evidence(storage):
    for hop in range(2):
        frontier = [key for key in storage.native_items if storage.depths.get(key) == hop]
        if not frontier:
            continue
        extra = [key for key in frontier if storage.native_items[key]['stage'] in {'evidence_extension', 'evidence_continuation'}]
        _expand_entities(storage, extra, hop)
        connections = storage.service.connection_provider(storage.actor, storage.member,
            storage.snapshot['record_cutoff'], frontier)
        if connections['unread']:
            storage.gaps.append({'code': 'connection_coverage_incomplete', 'unread': connections['unread']})
        fresh = storage.fresh()
        for link in connections['connections']:
            identity = link['event_id']
            if identity not in fresh['events'] or identity in storage.done:
                continue
            storage.add_paths({identity: [{**link['path'], 'hop': hop + 1}]})
            storage.add_item(identity, stage='evidence_extension')


def search(storage, *, expansion_enabled):
    # Validate the old proof before new recall; another physical binding may
    # not restore an invalidated continuation target within this same cursor.
    _resume(storage, prepare=True)
    if not storage.runtime.allowed:
        result = {'items': [], '_timings': {}, 'empty_index': True, 'model_calls': []}
        config = {}
    else:
        try:
            result = search_sag(storage.runtime, storage.query, expansion_enabled=expansion_enabled)
            config = result['config']
            storage.remember(result)
            storage.failures.extend({'code': row['code'], 'message': '部分检索向量未通过完整性检查。'}
                for row in result['vector_evidence']['failures'])
            storage.deferred.update(result['vector_evidence']['deferred_event_ids'])
            seeds = set(result['query_event_ids']) | set(result['entity_event_ids'])
            for row in result['items']:
                storage.add_item(row['event_id'], stage='seed' if row['event_id'] in seeds else 'entity_expansion',
                    score=row['score'], model_selected=row['model_selected'])
            for identity in result['vector_evidence']['query_probes']:
                if identity not in storage.paths and identity in storage.vector_hits:
                    storage.add_paths({identity: [{'route': 'query_probe', 'text_hits': [], 'text_rank': None,
                        'vector_hits': storage.vector_hits[identity], 'vector_rank': 1}]})
        except OperationCancelledError:
            raise
        except SerenitaError:
            raise
        except ProviderChatCompletionError as exc:
            raise SerenitaError('upstream_failure', exc.code or 'MEMORY_QUERY_MODEL_FAILED', 'SAG 查询模型调用失败。') from exc
        except Exception as exc:
            raise SerenitaError('upstream_failure', 'MEMORY_QUERY_FAILED', 'SAG 查询未完成。') from exc
    _resume(storage)
    if expansion_enabled:
        _extend_evidence(storage)
    result['items'] = list(storage.native_items.values())
    return result, config
