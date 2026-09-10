"""Shared model parameter structure adaptation and JSON Schema validation."""
import json
from functools import lru_cache
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match


@lru_cache(maxsize=128)
def _validator(encoded: str) -> Draft202012Validator:
    schema = json.loads(encoded)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def validate_parameters(value: Any, schema: dict | bool, *, label: str) -> None:
    json.dumps(value, allow_nan=False)
    validator = _validator(json.dumps(schema, sort_keys=True, ensure_ascii=False))
    error = best_match(validator.iter_errors(value))
    if error is None:
        return
    path = label + ''.join(f'[{part}]' if isinstance(part, int) else f'.{part}' for part in error.absolute_path)
    names = {'array': '数组', 'object': '对象', 'string': '字符串', 'integer': '整数', 'number': '数字', 'boolean': '布尔值', 'null': '空值'}
    if error.validator == 'type' and isinstance(error.validator_value, str):
        message = f'必须是{names.get(error.validator_value, error.validator_value)}。'
    elif error.validator in ('maxLength', 'minLength', 'maxItems', 'minItems', 'maximum', 'minimum'):
        message = f'不符合 {error.validator}={error.validator_value} 约束。'
    else:
        message = f'不符合 {error.validator} 约束，请按工具参数结构修正。'
    raise ValueError(path + ' ' + message)


def model_parameters(model, *, describe=None, partial=False):
    """Inline local references without discarding constraints beside a reference."""
    raw = model.model_json_schema()
    definitions = raw.get('$defs', {})
    annotations = {'description', 'default', 'examples', 'deprecated', 'readOnly', 'writeOnly'}

    def expand(value, stack=()):
        if isinstance(value, list):
            return [expand(item, stack) for item in value]
        if not isinstance(value, dict):
            return value
        reference = value.get('$ref')
        if reference:
            if not reference.startswith('#/$defs/') or reference in stack:
                raise ValueError('工具参数结构只接受无环的本地引用。')
            name = reference[len('#/$defs/'):].replace('~1', '/').replace('~0', '~')
            result = expand(definitions[name], (*stack, reference))
            siblings = expand({key: item for key, item in value.items() if key != '$ref'}, stack)
            constraints = {key: item for key, item in siblings.items() if key not in annotations}
            if constraints:
                result = {**result, 'allOf': [*result.get('allOf', []), constraints]}
            result.update({key: item for key, item in siblings.items() if key in annotations})
            return result
        result = {key: expand(item, stack) for key, item in value.items() if key not in ('$defs', 'title')}
        if describe:
            for name, prop in result.get('properties', {}).items():
                if not prop.get('description'):
                    prop['description'] = describe(name, prop)
        return result

    result = expand(raw)
    if partial:
        result.pop('required', None)
        result['minProperties'] = 1
    return result
