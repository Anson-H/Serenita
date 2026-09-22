"""Mutable processing-state fields excluded from immutable evidence content."""

RUNTIME_FIELDS = {'model_id', 'result_references', 'outcome_reason',
    'gaps', 'processing_status', 'error_code', 'error_message', 'retry_after', 'started_commit_id', 'updated_commit_id'}

