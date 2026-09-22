"""Read bounded graph projections under one authorized memory snapshot."""
import json
from backend.app.core.errors import SerenitaError
from backend.app.core.pagination import seek_cursor, seek_position
from backend.app.schemas.memory.values import canonical_uuid
from backend.app.domain.memory.references import object_reference, reference_key
from backend.app.repositories.memory.reading.object_projection import reference, stored_references
from backend.app.repositories.memory.facts.relations import event_relations_at


class MemoryGraphRepository:
    def __init__(self, repository):
        self.repository = repository

    def read(self, actor, member, request):
        return self._episode(actor, member, request) if request.episode_id else self._memory(actor, member, request)

    def _episode(self, actor, member, request):
        repo = self.repository
        with repo._transaction(actor, member) as (access, db):
            scope = ['event_graph', actor, member, access.permission,
                     access.grant_updated_at.isoformat() if access.grant_updated_at else 'owner',
                     request.model_dump(mode='json', exclude={'cursor', 'record_cutoff', 'limit', 'edge_limit','edge_cursor'})]
            try:
                position = seek_position(request.cursor, scope=scope, size=2)
                cutoff = repo._cutoff(db, access, int(position[0]) if position else request.record_cutoff)
                last = canonical_uuid(position[1]) if position else None
                if position and request.record_cutoff is not None and request.record_cutoff != cutoff:
                    raise ValueError()
            except ValueError as exc:
                raise SerenitaError('invalid_input', 'MEMORY_GRAPH_CURSOR', '图分页游标不属于当前成员、权限或读取范围。') from exc
            episode = repo._require(db, access, 'episode', request.episode_id, cutoff=cutoff)
            scan_limit=max(request.limit*4,100)
            rows = db.execute('SELECT d.event_id FROM event_episode d JOIN commits c USING(commit_id) '
                'WHERE d.account_id=? AND d.member_id=? AND d.episode_id=? AND c.sequence<=? AND (? IS NULL OR d.event_id>?) ORDER BY d.event_id LIMIT ?',
                (access.account_id, member, request.episode_id, cutoff,last,last,scan_limit+1)).fetchall()
            page, unavailable,visited = [], False,0
            for raw in rows[:scan_limit]:
                visited+=1
                decision = repo._record(db, access, 'episode_membership', raw['event_id'], cutoff=cutoff)
                if not repo._visible(db, access, decision):
                    unavailable = True
                    continue
                event = repo._require(db, access, 'event', decision['event_id'], cutoff=cutoff)
                if repo._matches(db, access, event, request):
                    page.append((event, decision))
                    if len(page)==request.limit:break
            following = seek_cursor(scope, [str(cutoff), rows[visited-1]['event_id']]) if visited<len(rows) else None
            objects = [repo._project(db, access, episode, cutoff, request)]
            memberships, nodes = [], []
            for event, decision in page:
                projected = repo._project(db, access, event, cutoff, request)
                nodes.append(object_reference(projected))
                objects.extend([projected, repo._project(db, access, decision, cutoff, request)])
                memberships.append(object_reference(decision))
            result = self._base(request, cutoff, objects, nodes, following)
            result.update(graph_kind='event_graph', episode=object_reference(episode), memberships=memberships)
            complete_population=not following and last is None and not unavailable
            result['coverage'].update(matching_events=len(page) if complete_population else None,returned_events=len(page),
                scanned_memberships=visited,complete_population=complete_population)
            if unavailable:
                result['unread'].append({'reason': 'membership_evidence_unavailable'})
            from functools import cache
            @cache
            def contains(identity):
                found=db.execute('SELECT d.event_id FROM event_episode d JOIN commits c USING(commit_id) '
                    'WHERE d.account_id=? AND d.member_id=? AND d.episode_id=? AND d.event_id=? AND c.sequence<=? ORDER BY c.sequence DESC LIMIT 1',
                    (access.account_id,member,request.episode_id,identity,cutoff)).fetchone()
                if not found:return False
                decision=repo._record(db,access,'episode_membership',found[0],cutoff=cutoff)
                if not repo._visible(db,access,decision):
                    result['unread'].append({'reason':'membership_evidence_unavailable'});return False
                event=repo._record(db,access,'event',identity,cutoff=cutoff)
                return repo._visible(db,access,event) and repo._matches(db,access,event,request)
            self._edges(result,access,db,request,episode_contains=contains)
            self._finish(result, request)
            return result

    def _memory(self, actor, member, request):
        query = request.model_dump(mode='json', exclude={'episode_id', 'edge_limit','edge_cursor'})
        from backend.app.schemas.memory.append import MemoryQuery
        filters = MemoryQuery.model_validate({key: value for key, value in query.items() if key not in {'references', 'business_changes'}})
        if request.business_changes:
            base = self.repository.evidence.read_change_observation(actor, member, [ref.model_dump() for ref in request.business_changes])
        elif request.references:
            base = self.repository.read(actor, member, request.references, query=filters)
        else:
            base = self.repository.query(actor, member, filters)
        result = self._base(request, base['record_cutoff'], base['objects'],
                            [object_reference(row) for row in base['objects']], base['next_cursor'])
        result.update(graph_kind='memory_graph')
        result['coverage'].update(base['coverage'])
        if not result['nodes']:
            if request.edge_cursor:
                raise SerenitaError('invalid_input','MEMORY_GRAPH_CURSOR','边续读的对象范围已不可读取，请重新读取。')
            self._finish(result, request)
            return result
        repo = self.repository
        with repo._transaction(actor, member) as (access, db):
            for row in base['objects']:
                if not repo._visible(db,access,row):
                    raise SerenitaError('forbidden','MEMORY_GRAPH_SOURCE_CHANGED','图的来源权限已变化，请重新读取。')
            self._edges(result,access,db,request)
        self._finish(result, request)
        return result

    @staticmethod
    def _base(request, cutoff, objects, nodes, following):
        return {'member_id': objects[0]['member_id'] if objects else None, 'record_cutoff': cutoff,
                'target_time': request.target_time.model_dump(mode='json') if request.target_time else None,
                'view': request.view, 'objects': list(objects), 'nodes': nodes, 'edges': [], 'relations': [],
                'coverage': {}, 'gaps': [], 'unread': [], 'next_cursor': following, 'next_edge_cursor':None,'edge_continuation':None,'continuations': []}

    def _edges(self,result,access,db,request,*,episode_contains=None):
        """Seek two bounded streams; positions include filtered/restricted rows."""
        repo,cutoff=self.repository,result['record_cutoff']
        stored={}
        if episode_contains is None:
            for row in result['objects']:
                if row['object_type'] == 'event':
                    continue
                start=object_reference(row)
                for target,path in stored_references(row):
                    # Evidence stays readable; only Event Relations draw Event edges.
                    if target['object_type'] == 'event':
                        continue
                    key=json.dumps([reference_key(start),path,reference_key(target)],ensure_ascii=False,separators=(',',':'))
                    stored[key]=(start,target,path)
        scope=['memory_graph_edges',result['graph_kind'],access.actor_account_id,access.account_id,access.member_id,access.permission,
            access.grant_updated_at.isoformat() if access.grant_updated_at else 'owner',
            request.model_dump(mode='json',exclude={'edge_cursor','record_cutoff','edge_limit'}),result['nodes'],sorted(stored)]
        phase,after=(1 if episode_contains is not None else 0),''
        try:
            position=seek_position(request.edge_cursor,scope=scope,size=3)
            if position:
                if int(position[0])!=cutoff or position[1] not in {'0','1'}:raise ValueError()
                phase,after=int(position[1]),position[2]
                if episode_contains is not None and phase!=1:raise ValueError()
            seek=None
            if phase == 1 and after:
                seek=json.loads(after)
                if not isinstance(seek,list) or len(seek)!=2 or int(seek[0])<1:raise ValueError()
                canonical_uuid(seek[1])
        except (ValueError,TypeError,KeyError) as exc:
            raise SerenitaError('invalid_input','MEMORY_GRAPH_CURSOR','边分页游标不属于当前对象页、权限或读取范围，请重新读取。') from exc

        def continuation(next_phase,coordinate):
            token=seek_cursor(scope,[str(cutoff),str(next_phase),coordinate])
            result['next_edge_cursor']=token
            result['edge_continuation']={**request.model_dump(mode='json',exclude_none=True),'record_cutoff':cutoff,'edge_cursor':token}
            result['unread'].append({'reason':'graph_edge_budget','limit':request.edge_limit})

        if phase==0:
            keys=[key for key in sorted(stored) if not after or key>after]
            scan_budget=max(100,request.edge_limit*4)
            for index,key in enumerate(keys):
                start,target,path=stored[key]
                actual=repo._record(db,access,target['object_type'],target['object_id'],cutoff=cutoff,version=target.get('version'),item_id=target.get('item_id'))
                if repo._visible(db,access,actual):
                    result['edges'].append({'edge_kind':'stored_reference','from':start,'to':target,'field_path':path,'basis':start})
                else:result['unread'].append({'reason':'graph_reference_unavailable'})
                if len(result['edges'])==request.edge_limit or index+1==scan_budget:
                    continuation(0,key) if index+1<len(keys) else continuation(1,'')
                    return
            phase,seek=1,None
        if phase==1:
            event_ids=[value['object_id'] for value in result['nodes'] if value['object_type']=='event']
            if event_ids:
                pairs=event_relations_at(repo,db,access,cutoff,event_ids,request.edge_limit-len(result['edges']),after_position=seek)
                result['unread'].extend(value for value in pairs['unread'] if value['reason']!='relation_pair_budget')
                for pair in pairs['pairs']:
                    relation=pair['relation']
                    if relation and (episode_contains is None or all(episode_contains(relation[side]) for side in ('from_event_id','to_event_id'))):
                        self._event_edge(result,pair,request)
                if pairs['next_position']:
                    continuation(1,json.dumps(pairs['next_position'],separators=(',',':')));return

    def _event_edge(self, result, pair, request):
        row = pair['relation']
        result['objects'].append(row)
        result['relations'].append(row)
        result['edges'].append({'edge_kind': 'event_relation',
            'from': reference('event', row['from_event_id']), 'to': reference('event', row['to_event_id']),
            'relation': object_reference(row), 'relation_type': row['relation_type'],
            'direction': 'symmetric' if row.get('symmetric') else 'from_to'})

    @staticmethod
    def _finish(result, request):
        result['objects'] = list({reference_key(object_reference(row)): row for row in result['objects']}.values())
        visible = {reference_key(value) for value in result['nodes']}
        boundary = {reference_key(edge[side]): edge[side] for edge in result['edges'] for side in ('from', 'to')
                    if reference_key(edge[side]) not in visible}
        result['boundary_references'] = list(boundary.values())
        result['unread'] = list({json.dumps(value, sort_keys=True): value for value in result['unread']}.values())
        unknown = [object_reference(row) for row in result['objects'] if row['object_type'] == 'event'
                   and ((row['occurrence_time'] or {}).get('uncertainty') != 'exact' or (row['occurrence_time'] or {}).get('unknown'))]
        if unknown:
            result['gaps'].append({'reason': 'event_time_unknown', 'references': unknown})
        if result['next_cursor']:
            result['continuations'].append({**request.model_dump(mode='json',exclude={'edge_cursor'},exclude_none=True), 'record_cutoff': result['record_cutoff'], 'cursor': result['next_cursor']})
        if result['edge_continuation']:
            result['continuations'].insert(0,result['edge_continuation'])
        result['complete'] = not result['next_cursor'] and not result['next_edge_cursor'] and not result['unread']
        result['coverage'].update(returned_nodes=len(result['nodes']), returned_edges=len(result['edges']),
                                  graph_edges_persisted=0, boundary_references=len(boundary))

