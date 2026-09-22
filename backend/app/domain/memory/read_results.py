"""Project authorized memory evidence for API and model-visible results."""

def readable_change(change):
    """Expose the evidence identity and Markdown without raw ledger payloads."""
    from backend.app.domain.memory.source_markdown import source_markdown, source_title
    return {**{key: change[key] for key in ('source_database', 'change_id', 'field_path',
        'resource_type', 'resource_id', 'operation_kind', 'recorded_at')},
        'title': source_title(change), 'content_text': source_markdown(change)}


def readable_result(result):
    """Project public evidence after authorization and internal receipt creation."""
    output = dict(result)
    if 'business_changes' in output:
        output['business_changes'] = [readable_change(change) for change in output['business_changes']]
    if isinstance(output.get('evidence'), dict):
        output['evidence'] = readable_result(output['evidence'])
    return output

