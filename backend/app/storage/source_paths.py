"""Registered source locations and non-mutating, symlink-safe file checks."""
from pathlib import Path
from uuid import UUID

SOURCE_DATABASES = ('members.db', 'reports.db', 'medical_logs.db', 'medications.db', 'body_metrics.db')


def registered_source_path(paths, account, database):
    if not isinstance(account, str) or str(UUID(account)) != account:
        raise ValueError('Invalid source account')
    if database not in {*SOURCE_DATABASES, 'memory.db'}:
        raise ValueError('Unregistered source database')
    return paths.root / 'accounts' / account / f'{database[:-3]}/db_storage/{database}'


def safe_existing_file(path, boundary):
    path, boundary = Path(path), Path(boundary)
    relative = path.relative_to(boundary)
    cursor = boundary
    if cursor.is_symlink():
        return False
    for component in relative.parts:
        if component in {"", ".", ".."}:
            return False
        cursor /= component
        if cursor.is_symlink():
            return False
    return path.is_file()
