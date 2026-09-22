"""Revalidate complete, bounded SAG paths against current source permissions."""
from collections import defaultdict

from backend.app.core.values import digest as fingerprint


def authorized_chains(repo, actor, member, cutoff, paths, snapshot, query, *, diagnostic_ids=(), verification=None):
    """An available final edge cannot restore a disconnected intermediate node."""
    links = {(row['event_id'], row['entity_id']) for row in snapshot['links']}
    chains, truncated, permission_changed = defaultdict(list), False, False
    from backend.app.repositories.memory.reading.sag_paths import semantic_hits, verified_semantic_bindings, semantic_hit_visible
    semantic_verified = verified_semantic_bindings(repo, actor, member, cutoff, semantic_hits(paths), snapshot) if semantic_hits(paths) else set()
    with repo._transaction(actor, member) as (access, db):
        checked = {}
        # Snapshots supplied by the caller describe the fixed index cutoff.
        # Source permissions may have changed since they were read.
        descriptions = {identity for identity in paths if identity in snapshot['events'] and
            repo._visible(db, access, repo._record(db, access, 'event', identity, cutoff=cutoff))}
        permission_changed = bool(set(paths).difference(descriptions))
        # Unread group members may be outside the traversal budget. Their
        # index identities still require a live check before a gap names them.
        permission_changed |= any(not repo._visible(db, access, snapshot['events'].get(identity))
            for identity in diagnostic_ids)
        needed_entities = set()
        needed_entities.update(step['entity_id'] for steps in paths.values() for step in steps if step['route'] in {'entity', 'entity_vector'})
        entities = {identity: row for identity in needed_entities if identity in snapshot['entities'] and
            (row := repo._record(db, access, 'entity', identity, cutoff=cutoff)) and repo._visible(db, access, row)}
        permission_changed |= bool(needed_entities.difference(entities))
        from backend.app.repositories.memory.indexing.index_repository import MemoryIndexRepository
        from backend.app.repositories.memory.reading.search_hits import check_seed, hit_lookup, verify_hit_bindings
        vectors = MemoryIndexRepository(repo).vectors
        lookup = hit_lookup(snapshot, query)
        verified = verify_hit_bindings(vectors, snapshot, lookup,
            [hit for steps in paths.values() for step in steps if step['route'] in {'seed', 'query_probe', 'entity_seed', 'entity_vector'} for hit in step['vector_hits']], verification=verification)

        def edge_visible(step, identity):
            nonlocal permission_changed
            via = step['via_event_id']
            if via not in descriptions:
                return False
            if step['route'] in {'entity', 'entity_vector'}:
                entity = step['entity_id']
                valid = entity in entities and (via, entity) in links and (identity, entity) in links
                if step['route'] == 'entity_vector':
                    valid &= step['entity_hit']['entity_id'] == entity and semantic_hit_visible(repo, db, access,
                        step['entity_hit'], semantic_verified, snapshot, event_id=via)
                    score_step = {'text_hits': [], 'text_rank': None, 'vector_hits': step['vector_hits'], 'vector_rank': 1}
                    checked_score, changed = check_seed(repo, access, db, cutoff, identity, score_step, snapshot, lookup, verified)
                    valid &= bool(checked_score['vector_hits']) and not changed
                    permission_changed |= not valid
                return valid
            if step['route'] not in {'episode', 'event_relation'} or not step.get('references'):
                return False
            key = fingerprint(step['references'])
            if key not in checked:
                checked[key] = all(repo._visible(db, access, repo._record(db, access,
                    ref['object_type'], ref['object_id'], cutoff=cutoff, version=ref.get('version')))
                    for ref in step['references'])
                permission_changed |= not checked[key]
            return checked[key]

        for depth in range(3):
            for identity, steps in paths.items():
                if identity not in descriptions:
                    continue
                for step in steps:
                    if step['route'] in {'seed', 'query_probe', 'entity_seed'}:
                        if depth != 0:
                            continue
                        live, changed = check_seed(repo, access, db, cutoff, identity, step, snapshot, lookup, verified)
                        permission_changed |= changed
                        if step['route'] == 'entity_seed':
                            valid = semantic_hit_visible(repo, db, access, step['entity_hit'], semantic_verified,
                                snapshot, event_id=identity) and bool(live['vector_hits']) and not changed
                            permission_changed |= not valid
                            if not valid:
                                continue
                        if not live['text_hits'] and not live['vector_hits']:
                            continue
                        additions = [[{**live, 'event_id': identity}]]
                    else:
                        if step.get('hop') != depth or not edge_visible(step, identity):
                            continue
                        additions = [chain + [{**step, 'event_id': identity}]
                            for chain in chains.get(step['via_event_id'], []) if len(chain) == depth
                            and identity not in {part['event_id'] for part in chain}]
                    for chain in additions:
                        if chain in chains[identity]:
                            continue
                        if len(chains[identity]) >= 8:
                            truncated = True
                            continue
                        chains[identity].append(chain)
    return dict(chains), truncated, permission_changed
