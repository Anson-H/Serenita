"""Bounded immutable request positions. Contains no payloads or permissions."""
from collections import OrderedDict
from threading import Lock


_positions = OrderedDict()
_guard = Lock()
_MAX_ATTEMPTS = 256
_MAX_REQUESTS = 16384
_MAX_TOTAL_REQUESTS = 32768


def request_positions(repo, db, access, attempt):
    from backend.app.repositories.memory.processing.staging_scope import staging
    draft = staging(repo)
    view = draft.db if draft is not None else str(repo.path_for_account(access.account_id))
    key = (view, access.account_id, access.member_id, attempt)
    latest = db.execute('SELECT entry_sequence,entry_id FROM execution_entries WHERE attempt_id=? '
        'AND account_id=? AND member_id=? ORDER BY entry_sequence DESC LIMIT 1',
        (attempt, access.account_id, access.member_id)).fetchone()
    if latest is None:
        return []
    with _guard:
        saved = _positions.get(key)
    # This exact immutable boundary must still exist. Checking the key also
    # catches an explicitly recreated database at the same path or inode.
    valid = saved is not None and saved[0] <= latest['entry_sequence'] and db.execute(
        'SELECT 1 FROM execution_entries WHERE attempt_id=? AND entry_sequence=? AND entry_id=?',
        (attempt, saved[0], saved[1])).fetchone() is not None
    after, positions = (saved[0], list(saved[2])) if valid else (0, [])
    positions.extend((row['entry_id'], row['entry_sequence']) for row in db.execute(
        "SELECT entry_id,entry_sequence FROM execution_entries WHERE attempt_id=? AND account_id=? AND member_id=? "
        "AND entry_sequence>? AND entry_sequence<=? AND entry_kind='model_request' ORDER BY entry_sequence",
        (attempt, access.account_id, access.member_id, after, latest['entry_sequence'])))
    if len(positions) <= _MAX_REQUESTS:
        with _guard:
            current = _positions.get(key)
            if current is None or not valid or current[0] <= latest['entry_sequence']:
                _positions[key] = (latest['entry_sequence'], latest['entry_id'], tuple(positions))
                _positions.move_to_end(key)
            while len(_positions) > _MAX_ATTEMPTS or sum(len(value[2]) for value in _positions.values()) > _MAX_TOTAL_REQUESTS:
                _positions.popitem(last=False)
    return positions
