"""Read-only stage validation and one request boundary for bounded repairs.

Each model substep owns MAX_MODEL_ATTEMPTS total calls, including transport
failures. Runtime request caching must capture calls under current_step(), and
replay their recorded outcomes before allowing another physical request.
"""
from copy import deepcopy
import json

from jsonschema import Draft202012Validator
from pydantic import ValidationError

from backend.app.application.memory.sag.entity_names import normalize_entity_name
from backend.app.core import model_retry
from backend.app.core.model_retry import transient_network_error
from backend.app.domain.memory.model_output import parse_json
from backend.app.domain.memory.event_hierarchy import walk_events, output_path
from backend.app.schemas.memory.values import EventTime


class StageValidationError(ValueError):
    def __init__(self, errors):
        self.errors = errors
        first = errors[0]
        location = '.'.join(map(str, first.get('path', [])))
        super().__init__((location + '：' if location else '') + first['message'])


def require_valid(errors):
    if errors:
        raise StageValidationError(errors)


def diagnostic(path, message, code='MEMORY_STAGE_OUTPUT_INVALID'):
    return {'path': list(path), 'message': message, 'code': code}


def schema_errors(schema, value):
    return [diagnostic(error.absolute_path, error.message) for error in
            Draft202012Validator(schema).iter_errors(value)]


def model_errors(schema, value, path=()):
    try:
        schema.model_validate(deepcopy(value))
    except ValidationError as error:
        return [diagnostic([*path, *item['loc']], item['msg'])
                for item in error.errors(include_input=False, include_context=False)]
    return []


def parse_stage_output(output):
    if output.tool_calls or not output.has_final_stop:
        raise StageValidationError([diagnostic([], '阶段需要完整结束的结构化结果，不能返回工具调用。')])
    try:
        return parse_json(output.content)
    except json.JSONDecodeError as error:
        raise StageValidationError([diagnostic([], f'JSON 在第 {error.lineno} 行、第 {error.colno} 列解析失败：{error.msg}。返回完整 JSON，检查引号、逗号和结尾括号。',
            'MEMORY_STAGE_JSON_INVALID')]) from error
    except (ValueError, TypeError) as error:
        raise StageValidationError([diagnostic([], '返回值必须为合法 JSON 对象。')]) from error


def complete_once(complete, request):
    """Let the stage count transport failures and invalid answers together.

    The existing network adapter respects this context and executes only once.
    The model wrapper still observes every call, including cache replay.
    """
    with model_retry.retry_scope():
        return complete(request)


def wait_for_stage_retry(error, attempt, complete, *, check_running=None):
    from backend.app.application.memory.progress import report_model_retry
    report_model_retry(error, attempt)
    model_retry.wait_before_retry(check_running=check_running or getattr(complete, 'check_running', None))


def retry_errors(error):
    if isinstance(error, StageValidationError):
        return error.errors
    if transient_network_error(error):
        return None
    raise error


def extraction_errors(items, references, entity_catalog=None):
    """Validate references, occurrence values and exact catalog identities.

    Called only after JSON Schema has established the nested output shape.
    Does not replace null strings, trim identities, or rewrite supplied values.
    """
    errors = []
    catalog = {row['entity_id']: row for row in entity_catalog or []}
    for path, item in walk_events(items):
        position = output_path(path)
        for field in ('title', 'summary', 'content', 'category'):
            if not item[field].strip():
                errors.append(diagnostic([*position, field], '事件标题、摘要、正文和分类必须有实际文字。', 'MEMORY_SAG_CONTENT_EMPTY'))
        for number, reference in enumerate(item['references']):
            if type(reference) is not int or reference not in references:
                errors.append(diagnostic([*position, 'references', number],
                    'references 必须采用当前输入实际提供的来源单元整数 id。', 'MEMORY_SAG_REFERENCE_INVALID'))
        if item.get('occurrence_time') is not None:
            errors.extend(model_errors(EventTime, item['occurrence_time'], [*position, 'occurrence_time']))
        for number, mention in enumerate(item.get('entities', [])):
            base = [*position, 'entities', number]
            for field in ('name', 'type', 'description'):
                if not mention[field].strip() or (field == 'name' and not normalize_entity_name(mention[field])):
                    errors.append(diagnostic([*base, field], '实体名称、类型和说明必须有实际文字。'))
            for index, alias in enumerate(mention['aliases']):
                if not alias.strip():
                    errors.append(diagnostic([*base, 'aliases', index], '实体别名必须有实际文字。'))
            identity = mention['entity_id']
            if identity is None:
                continue
            if identity.strip().casefold() == 'null':
                errors.append(diagnostic([*base, 'entity_id'], 'entity_id 必须使用 JSON null，不能使用字符串 "null"。', 'MEMORY_ENTITY_ID_INVALID'))
            elif identity not in catalog:
                errors.append(diagnostic([*base, 'entity_id'], f'entity_id {identity!r} 不在当前输入的实体目录中；请逐字复制目录编号，无对应或不确定时填写 JSON null。', 'MEMORY_ENTITY_ID_INVALID'))
            elif mention['type'] != catalog[identity]['type']:
                errors.append(diagnostic([*base, 'type'], f'已有 entity_id 的 type 必须逐字复制为 {catalog[identity]["type"]!r}。', 'MEMORY_ENTITY_TYPE_INVALID'))
    if errors:
        return errors
    # Exercise the same pure identity matching used by the save service. The
    # synthetic namespace is local to this validation and is never persisted.
    from backend.app.application.memory.sag.entity_resolution import EntityResolver
    from backend.app.core.errors import SerenitaError
    resolver = EntityResolver(entity_catalog or [], '00000000-0000-0000-0000-000000000000', 'validation')
    for path, item in walk_events(items):
        identities = {}
        for number, mention in enumerate(item.get('entities', [])):
            try:
                identity = resolver._resolve_entity_id(mention)
                resolver._record_entity_aliases(identity, mention)
                key = (mention['type'], mention['name'])
                if key in identities and identities[key] != identity:
                    errors.append(diagnostic([*output_path(path), 'entities', number, 'entity_id'],
                        '同一事件中的相同实体名称与类型不能指向不同身份。', 'MEMORY_ENTITY_IDENTITY_CONFLICT'))
                identities[key] = identity
            except SerenitaError as error:
                errors.append(diagnostic([*output_path(path), 'entities', number], error.message, error.code))
    return errors


def facts_errors(value, source, originals):
    errors = []
    for index, fact in enumerate(value['facts']):
        for number, evidence in enumerate(fact['evidence']):
            ref, quote = evidence['reference'], evidence['quote']
            path = ['facts', index, 'evidence', number]
            if type(ref) is not int or ref not in source:
                errors.append(diagnostic([*path, 'reference'], 'evidence.reference 必须采用当前输入实际提供的来源单元整数 id。'))
            elif quote not in source[ref] or quote not in originals[ref]:
                errors.append(diagnostic([*path, 'quote'], 'evidence.quote 必须逐字摘自 reference 对应的当前输入和来源原文。'))
    return errors


def routing_errors(value, allowed):
    identity = value['episode_id']
    if identity is not None and identity not in allowed:
        return [diagnostic(['episode_id'], 'episode_id 必须逐字复制实际读取目录中的一个事项编号，或填写 JSON null。',
            'MEMORY_EPISODE_SELECTION_INVALID')]
    return []
