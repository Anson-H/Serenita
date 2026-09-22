"""Read evidenced Event and Episode connections for one bounded SAG hop."""
from collections import defaultdict

from backend.app.repositories.memory.facts.relations import event_relations_at


CONNECTION_LIMIT = 500


def _memberships(repo, db, access, cutoff, field, identities, unread):
    if not identities:
        return []
    assert field in {'event_id', 'episode_id'}
    placeholders = ','.join('?' for _ in identities)
    rows = db.execute('SELECT d.event_id FROM event_episode d JOIN commits c USING(commit_id) '
        f'WHERE d.account_id=? AND d.member_id=? AND d.{field} IN ({placeholders}) AND c.sequence<=? '
        'ORDER BY c.sequence,d.event_id LIMIT ?',
        (access.account_id, access.member_id, *sorted(identities), cutoff, CONNECTION_LIMIT + 1)).fetchall()
    if len(rows) > CONNECTION_LIMIT:
        unread.append({'reason': 'episode_membership_budget', 'limit': CONNECTION_LIMIT})
    result = []
    for found in rows[:CONNECTION_LIMIT]:
        row = repo._record(db, access, 'episode_membership', found['event_id'], cutoff=cutoff)
        if not repo._visible(db, access, row):
            unread.append({'reason': 'episode_membership_evidence_unavailable'})
        else:
            result.append(row)
    return result


def _reference(kind, identity, **values):
    return {'object_type': kind, 'object_id': identity, **values}


def event_connections(repo, actor, member, cutoff, event_ids):
    """Return actual edges; similarity, shared names and dates create no edges."""
    result = {'connections': [], 'unread': []}
    with repo._transaction(actor, member) as (access, db):
        cutoff = repo._cutoff(db, access, cutoff)
        if db is None or not event_ids:
            return result
        by_event = defaultdict(list)
        for identity in dict.fromkeys(event_ids):
            row = repo._record(db, access, 'event', identity, cutoff=cutoff)
            if repo._visible(db, access, row):
                by_event[row['event_id']].append(identity)
            else:
                result['unread'].append({'reason': 'connection_seed_unavailable'})
        edges = []
        def add(left, right, path):
            if left == right or left not in by_event:
                return
            if len(edges) < CONNECTION_LIMIT:
                edges.append((left, right, path))
            elif not any(row['reason'] == 'connection_edge_budget' for row in result['unread']):
                result['unread'].append({'reason': 'connection_edge_budget', 'limit': CONNECTION_LIMIT})
        relations = event_relations_at(repo, db, access, cutoff, list(by_event), limit=CONNECTION_LIMIT)
        result['unread'].extend(relations['unread'])
        for pair in relations['pairs']:
            relation = pair['relation']
            if relation is None:
                continue
            path = {'route': 'event_relation', 'relation_id': relation['relation_id'],
                'relation_type': relation['relation_type'],
                'from_event_id': relation['from_event_id'], 'to_event_id': relation['to_event_id'],
                'references': [_reference('event_relation', relation['relation_id'])]}
            add(pair['relation']['from_event_id'], pair['relation']['to_event_id'], path)
            add(pair['relation']['to_event_id'], pair['relation']['from_event_id'], path)
        source_memberships = _memberships(repo, db, access, cutoff, 'event_id', set(by_event), result['unread'])
        by_episode = defaultdict(list)
        for row in source_memberships:
            by_episode[row['episode_id']].append(row)
        for target in _memberships(repo, db, access, cutoff, 'episode_id', set(by_episode), result['unread']):
            for source in by_episode[target['episode_id']]:
                add(source['event_id'], target['event_id'], {'route': 'episode', 'episode_id': target['episode_id'],
                    'from_event_id': source['event_id'], 'to_event_id': target['event_id'],
                    'references': [_reference('episode_membership', source['event_id']), _reference('episode_membership', target['event_id']),
                        _reference('episode', source['episode_id'])]})
        target_events = {right for _, right, _ in edges}
        targets = defaultdict(list)
        if target_events:
            placeholders = ','.join('?' for _ in target_events)
            rows = db.execute('SELECT d.event_id FROM events d JOIN commits c USING(commit_id) '
                f'WHERE d.account_id=? AND d.member_id=? AND d.event_id IN ({placeholders}) AND c.sequence<=? '
                'ORDER BY c.sequence,d.event_id LIMIT ?',
                (access.account_id, member, *sorted(target_events), cutoff, CONNECTION_LIMIT + 1)).fetchall()
            if len(rows) > CONNECTION_LIMIT:
                result['unread'].append({'reason': 'connection_event_budget', 'limit': CONNECTION_LIMIT})
            for found in rows[:CONNECTION_LIMIT]:
                # These are index identities for already authorized Event
                # endpoints. Read the actual description only after admission
                # to the caller's shared description budget.
                targets[found['event_id']].append(found['event_id'])
            if target_events.difference(targets):
                result['unread'].append({'reason': 'connected_event_unavailable'})
        for left, right, path in edges:
            for start in by_event[left]:
                for end in targets[right]:
                    if len(result['connections']) >= CONNECTION_LIMIT:
                        result['unread'].append({'reason': 'connection_path_budget', 'limit': CONNECTION_LIMIT})
                        return result
                    result['connections'].append({'event_id': end, 'path': {**path, 'via_event_id': start}})
    return result
