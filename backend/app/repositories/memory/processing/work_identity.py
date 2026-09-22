"""Stable work locations and authoritative publication identity checks."""
from backend.app.schemas.memory.append import canonical_uuid

def work_path(paths, account, member, attempt_id):
    return (paths.memory_db(canonical_uuid(account)).parent.parent / 'work' /
            canonical_uuid(member) / canonical_uuid(attempt_id) / 'work.db')


def publication_committed(db, account, member, publication):
    if not isinstance(publication, dict) or db is None:
        return False
    commits = publication.get('commit_ids', [])
    return isinstance(commits, list) and bool(commits) and all(isinstance(identity, str) and db.execute(
        'SELECT 1 FROM commits WHERE commit_id=? AND account_id=? AND member_id=?',
        (identity, account, member)).fetchone() for identity in commits)

