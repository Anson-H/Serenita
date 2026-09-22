"""Read the currently authorized entity identities and aliases for extraction."""

def entity_catalog(repository, actor, member):
    """Load the member's readable identity catalog once for extraction."""
    with repository._transaction(actor, member) as (access, db):
        if db is None:
            return []
        catalog = {}
        for raw in db.execute('SELECT entity_id FROM entities WHERE account_id=? AND member_id=? ORDER BY entity_id',
                (access.account_id, member)):
            entity = repository._record(db, access, 'entity', raw['entity_id'])
            if repository._visible(db, access, entity):
                catalog[entity['entity_id']] = {'entity_id': entity['entity_id'], 'name': entity['canonical_name'],
                    'type': entity['entity_type'], 'aliases': [], '_alias_ids': []}
        for raw in db.execute('SELECT entity_id,name_id FROM entity_names WHERE account_id=? AND member_id=? ORDER BY entity_id,name_id',
                (access.account_id, member)):
            if raw['entity_id'] in catalog:
                alias = repository._record(db, access, 'entity_name', raw['entity_id'], item_id=raw['name_id'])
                if repository._visible(db, access, alias):
                    catalog[raw['entity_id']]['aliases'].append(alias['name'])
                    catalog[raw['entity_id']]['_alias_ids'].append(raw['name_id'])
        return list(catalog.values())

