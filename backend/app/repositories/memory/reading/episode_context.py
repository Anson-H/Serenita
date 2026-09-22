"""Read fixed scope catalogs and the recorded contents of selected episodes."""
from copy import deepcopy
from backend.app.core.errors import SerenitaError
from backend.app.domain.memory.references import object_reference, reference_key


def limited(rows):
    if len(rows) > 1000:
        raise SerenitaError('resource_limit', 'MEMORY_EPISODE_CONTEXT_LIMIT', '事项读取范围超过处理预算，尚未完成。')
    return rows


class MemoryEpisodeContextRepository:
    def __init__(self, repository):
        self.repository = repository

    def catalog(self, actor, member, cutoff):
        repo = self.repository
        with repo._transaction(actor, member) as (access, db):
            if db is None:
                return []
            rows = limited(db.execute(
                'SELECT v.episode_id FROM episodes v JOIN commits c USING(commit_id) '
                'WHERE v.account_id=? AND v.member_id=? AND c.sequence<=? '
                'ORDER BY v.episode_id LIMIT 1001', (access.account_id, member, cutoff)).fetchall())
            scopes = []
            for row in rows:
                episode = repo._record(db, access, 'episode', row['episode_id'], cutoff=cutoff)
                if repo._visible(db, access, episode):
                    scopes.append(episode)
            return scopes

    def contents(self, actor, member, episode_ids, cutoff, *, require_complete=False, include_revision=True):
        """Return references and fixed event memberships; never recall global events."""
        repo, references, groups = self.repository, {}, {}
        uncached = set()
        def include(row):
            if row is not None and repo._visible(db, access, row):
                ref = object_reference(row)
                references[reference_key(ref)] = ref
                return True
            if require_complete:
                raise SerenitaError('forbidden', 'MEMORY_EPISODE_CONTEXT_INCOMPLETE', '所选事项内容缺失或不可读取，尚未完成全部事件读取。')
            return False
        with repo._transaction(actor, member) as (access, db):
            from backend.app.repositories.memory.reading.prepared_reads import prepared_reads
            from backend.app.repositories.memory.reading.read_cache import access_key
            prepared = prepared_reads(repo, access)
            for episode_id in sorted(set(episode_ids)):
                cache_key = (*access_key(access), episode_id)
                cached = prepared.episode_contexts.get(cache_key) if prepared is not None else None
                if (cached is not None and cached['cutoff'] <= cutoff <= cached['through']
                        and (not require_complete or cached['complete'])
                        and cached['include_revision'] == include_revision):
                    groups[episode_id] = []
                    accepted = set()
                    for ref in cached['refs']:
                        row = repo._record(db, access, ref['object_type'], ref['object_id'],
                            version=ref.get('version'), item_id=ref.get('item_id'), cutoff=cutoff)
                        if include(row):
                            accepted.add(reference_key(ref))
                    groups[episode_id] = [identity for identity in cached['events']
                        if reference_key({'object_type': 'event', 'object_id': identity}) in accepted
                        and reference_key({'object_type': 'episode_membership', 'object_id': identity}) in accepted]
                    continue
                uncached.add(episode_id)
                repo._require(db, access, 'episode', episode_id, cutoff=cutoff)
                include(repo._record(db, access, 'episode', episode_id, cutoff=cutoff))
                groups[episode_id] = []
                rows = limited(db.execute(
                    'SELECT d.event_id FROM event_episode d JOIN commits c USING(commit_id) '
                    'WHERE d.account_id=? AND d.member_id=? AND d.episode_id=? AND c.sequence<=? '
                    'ORDER BY d.event_id LIMIT 1001', (access.account_id, member, episode_id, cutoff)).fetchall())
                for row in rows:
                    decision = repo._record(db, access, 'episode_membership', row['event_id'], cutoff=cutoff)
                    if include(decision):
                        event = repo._record(db, access, 'event', decision['event_id'], cutoff=cutoff)
                        if include(event):
                            groups[episode_id].append(event['event_id'])
                if include_revision:
                    for row in limited(db.execute(
                        'SELECT s.version FROM episode_revisions s JOIN commits c USING(commit_id) '
                        'WHERE s.account_id=? AND s.member_id=? AND s.episode_id=? AND c.sequence<=? '
                        'ORDER BY s.version DESC LIMIT 1', (access.account_id, member, episode_id, cutoff)).fetchall()):
                        include(repo._record(db, access, 'episode_revision', episode_id, version=row['version'], cutoff=cutoff))
            event_ids = sorted({identity for episode, ids in groups.items() if episode in uncached for identity in ids})
            group_sets = [set(ids) for ids in groups.values()]
            if event_ids:
                marks = ','.join('?' for _ in event_ids)
                rows = limited(db.execute(
                    'SELECT r.relation_id,r.from_event_id,r.to_event_id FROM event_relations r JOIN commits c USING(commit_id) '
                    f'WHERE r.account_id=? AND r.member_id=? AND r.from_event_id IN ({marks}) AND r.to_event_id IN ({marks}) '
                    'AND c.sequence<=? ORDER BY c.sequence LIMIT 1001',
                    (access.account_id, member, *event_ids, *event_ids, cutoff)).fetchall())
                for row in rows:
                    if any({row['from_event_id'], row['to_event_id']} <= group for group in group_sets):
                        include(repo._record(db, access, 'event_relation', row['relation_id'], cutoff=cutoff))
            limited(references)
            if prepared is not None:
                for episode in uncached:
                    ids = set(groups[episode])
                    selected = []
                    for ref in references.values():
                        kind, identity = ref['object_type'], ref['object_id']
                        if (kind in {'episode', 'episode_revision'} and identity == episode
                                or kind in {'event', 'episode_membership'} and identity in ids):
                            selected.append(ref)
                        elif kind == 'event_relation':
                            row = repo._record(db, access, kind, identity, cutoff=cutoff)
                            if {row['from_event_id'], row['to_event_id']} <= ids:
                                selected.append(ref)
                    head = repo._cutoff(db, access)
                    changed = db.execute("SELECT 1 FROM commits c WHERE c.account_id=? AND c.member_id=? AND c.sequence>? AND c.sequence<=? AND ("
                        "EXISTS(SELECT 1 FROM event_episode m WHERE m.commit_id=c.commit_id AND m.episode_id=?) OR "
                        "EXISTS(SELECT 1 FROM episode_revisions v WHERE v.commit_id=c.commit_id AND v.episode_id=?) OR "
                        "EXISTS(SELECT 1 FROM event_relations r JOIN event_episode m ON m.event_id=r.from_event_id WHERE r.commit_id=c.commit_id AND m.episode_id=?)) LIMIT 1",
                        (access.account_id, member, cutoff, head, episode, episode, episode)).fetchone() if head > cutoff else None
                    prepared.episode_contexts[(*access_key(access), episode)] = {
                        'cutoff': cutoff, 'through': cutoff if changed else head,
                        'refs': deepcopy(selected), 'events': list(groups[episode]), 'complete': require_complete, 'include_revision': include_revision}
        return list(references.values()), groups


def advance_episode_contexts(prepared, access, written, before_cutoff, commit):
    """Advance cached scopes using this transaction's committed objects only."""
    from backend.app.repositories.memory.reading.read_cache import access_key
    scope = access_key(access)
    for key, cached in list(prepared.episode_contexts.items()):
        if key[:-1] != scope:
            continue
        if cached['through'] != before_cutoff:
            del prepared.episode_contexts[key]
            continue
        episode = key[-1]
        refs = {reference_key(ref): ref for ref in cached['refs']}
        events = set(cached['events'])
        changed = False
        for row in written.get('episode_memberships', []):
            if row['episode_id'] == episode:
                changed = True
                events.add(row['event_id'])
                for kind in ('event', 'episode_membership'):
                    ref = {'object_type': kind, 'object_id': row['event_id']}
                    refs[reference_key(ref)] = ref
        for row in written.get('episode_revisions', []):
            if cached['include_revision'] and row['episode_id'] == episode:
                changed = True
                refs = {key: ref for key, ref in refs.items() if ref['object_type'] != 'episode_revision'}
                ref = {'object_type': 'episode_revision', 'object_id': episode, 'version': row['version']}
                refs[reference_key(ref)] = ref
        for row in written.get('event_relations', []):
            if {row['from_event_id'], row['to_event_id']} <= events:
                changed = True
                ref = {'object_type': 'event_relation', 'object_id': row['relation_id']}
                refs[reference_key(ref)] = ref
        cached.update(through=commit['sequence'], refs=list(refs.values()), events=sorted(events))
        if changed:
            cached['cutoff'] = commit['sequence']
