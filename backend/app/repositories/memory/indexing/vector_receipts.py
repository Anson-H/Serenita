"""Successful vector storage results valid only while the binding lock is held."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy


_active = ContextVar('memory_vector_receipts', default=())


@contextmanager
def vector_receipt_scope(path, account, binding):
    token = _active.set((*_active.get(), (str(path.resolve()), account, binding, {})))
    try:
        yield
    finally:
        _active.reset(token)


def remembered_vector(vectors, account, space, identity, row=None):
    key = (vectors.index_name, space['space_id'], identity)
    for path, owner, binding, receipts in reversed(_active.get()):
        if path != str(vectors.path(account).resolve()) or owner != account:
            continue
        if row is not None:
            if row['binding_id'] == binding:
                receipts[key] = deepcopy(row)
                return None
        elif key in receipts:
            return deepcopy(receipts[key])
    return None
