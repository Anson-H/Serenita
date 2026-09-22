"""Execution checkpoints contain validated results, never inferred progress."""
from backend.app.core.values import strict_digest as digest
from copy import deepcopy

from backend.app.core.errors import SerenitaError

EXECUTION_CONTRACT_VERSION = 4


def contract_fingerprint():
    from backend.app.application.memory.prompt_config import PROMPT_ROOT
    from backend.app.core.token_counting import tokenizer_manifest
    from backend.app.core.model_retry import MAX_MODEL_ATTEMPTS, MODEL_RETRY_DELAY_SECONDS
    return digest({'version': EXECUTION_CONTRACT_VERSION, 'prompts': {p.name: p.read_text(encoding='utf-8')
        for p in sorted(PROMPT_ROOT.glob('*.yaml'))}, 'context_tokenizers': tokenizer_manifest(),
        'model_retry': {'max_attempts':MAX_MODEL_ATTEMPTS,'delay_seconds':MODEL_RETRY_DELAY_SECONDS,
            'network_structure_and_domain_share_persisted_substep_budget':True}})


def active_draft():
    from backend.app.repositories.memory.processing.staging_scope import staging
    return staging()


def checkpoint_metadata(draft, key, value, pipeline=None):
    """Retain the execution contract and actual inputs, without credentials."""
    from backend.app.application.memory.prompt_config import MemoryPromptConfig
    from backend.app.core.time import local_now
    stage = key.split(':', 1)[0]
    if stage == 'validated':
        stage = key.split(':', 2)[1]
    elif stage == 'extraction':
        stage = 'sag_facts' if key.startswith('extraction:sag_fact_extract:') else 'sag_extract'
    elif stage in {'routing', 'episode_search_catalog'}:
        stage = 'episode_search'
    schema_hash = None
    if stage in {'sag_extract', 'sag_facts', 'episode_search', 'event_organization', 'revisions'}:
        schema_hash = digest(MemoryPromptConfig.load(stage).schema('output'))
    return {'execution_contract_version': EXECUTION_CONTRACT_VERSION,
        'saved_at': local_now().isoformat(timespec='microseconds'),
        'contract_fingerprint': draft.work.get('contract'), 'schema_fingerprint': schema_hash,
        'input_digest': digest(value), 'model_snapshot': draft.work.get('model_snapshot'),
        'retry_epoch': draft.work.get('retry_epoch', 0),
        'request_counts': draft.work.request_counts(),
        'dependencies': list(pipeline.state.references.values()) if pipeline is not None else [],
        'operation_ids': draft.checkpoint_operation_ids()}


def freeze_input(key, factory):
    draft = active_draft()
    if draft is None:
        return factory()
    name = 'input:' + key
    saved = draft.work.get(name)
    if saved is not None:
        verify_saved(saved, {})
        verify_saved(saved, {'input_digest': saved.get('value')})
        return deepcopy(saved['value'])
    value = factory()
    draft.checkpoint(name, {'value': value, 'metadata': checkpoint_metadata(draft, key, value)})
    return value


def verify_saved(saved, values):
    if not isinstance(saved, dict) or not isinstance(saved.get('metadata'), dict) or any(saved['metadata'].get(key) != digest(value)
            for key, value in values.items()):
        raise SerenitaError('conflict', 'MEMORY_CHECKPOINT_DAMAGED',
            '检查点内容与保存摘要不一致，已保留工作数据，请从头重新处理。')


def run_checkpoint(key, function, pipeline=None):
    draft = active_draft()
    if draft is None:
        return function()
    name = 'step:' + key
    input_key = 'input:' + key.removeprefix('validated:')
    saved = draft.work.get(name)
    if saved is not None:
        verify_saved(saved, {})
        verify_saved(saved, {'result_digest': saved.get('result'), 'state_digest': saved.get('pipeline'),
            'input_digest': draft.work.get(input_key)})
        if pipeline is not None:
            pipeline.guard()
            pipeline.restore_state(saved['pipeline'])
            pipeline.retain(saved.get('result'))
        recovery_id = draft.work.get('active_recovery_id')
        if recovery_id:
            from backend.app.repositories.memory.processing.checkpoints import append_recovery
            append_recovery(draft.repo, draft.actor, draft.member, draft.attempt_id,
                'reuse-' + recovery_id + '-' + key, 'auto',
                {'step_id': key, 'reused': True,
                    'updated_at': saved.get('metadata', {}).get('saved_at')},
                draft.work.get('retry_epoch', 0))
        return deepcopy(saved.get('result'))
    result = function()
    state = {}
    if pipeline is not None:
        state = pipeline.export_state()
    fixed_input = draft.work.get(input_key)
    draft.checkpoint(name, {'result': result, 'pipeline': state,
        'metadata': {**checkpoint_metadata(draft, key, fixed_input, pipeline),
            'result_digest': digest(result), 'state_digest': digest(state)}})
    return result


def require_contract(work):
    fingerprint = contract_fingerprint()
    prior = work.get('contract')
    if prior is not None and prior != fingerprint:
        raise SerenitaError('conflict', 'MEMORY_CHECKPOINT_CONTRACT_CHANGED',
            '提示词、Schema 或执行契约已变化，保留检查点，请从头重新处理。')
    if prior is None:
        work.put('contract', fingerprint)
