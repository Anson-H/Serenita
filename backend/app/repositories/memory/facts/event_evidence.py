"""Read the direct immutable business-change references of an Event."""

def event_references(connection, access, event_id):
    if connection is None:
        return []
    return [dict(row) for row in connection.execute(
        'SELECT source_database,change_id,field_path FROM event_evidence WHERE account_id=? AND member_id=? AND event_id=? '
        'ORDER BY source_database,change_id,field_path', (access.account_id, access.member_id, event_id))]

