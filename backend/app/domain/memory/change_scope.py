"""Health content eligible for memory, shared by intake and change listings."""

# Originals remain readable evidence. Storage and association changes belong
# exclusively to the business ledger, not to memory source contents.
ATTACHMENT_CHANGE_TYPES = frozenset({'report_source', 'medication_source', 'body_file'})
ATTACHMENT_FIELD_ROOTS = {'report': '/sources', 'body_record': '/files'}


def memory_change_fields(resource_type, fields):
    if resource_type in ATTACHMENT_CHANGE_TYPES:
        return []
    root = ATTACHMENT_FIELD_ROOTS.get(resource_type)
    return [field for field in fields if root is None or
            (field['field_path'] != root and not field['field_path'].startswith(root + '/'))]
