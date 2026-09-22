"""Shared model parameter structure adaptation and JSON Schema validation."""
import json
from copy import deepcopy
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
    errors = list(validator.iter_errors(value))
    if not errors:
        return
    messages = []
    for original in errors[:8]:
        error = best_match([original])
        message = _parameter_error(error, label)
        if message not in messages:
            messages.append(message)
    raise ValueError('；'.join(messages))


def _parameter_error(error, label):
    path = label + ''.join(f'[{part}]' if isinstance(part, int) else f'.{part}' for part in error.absolute_path)
    names = {'array': '数组', 'object': '对象', 'string': '字符串', 'integer': '整数', 'number': '数字', 'boolean': '布尔值', 'null': '空值'}
    if error.validator == 'type':
        expected = error.validator_value if isinstance(error.validator_value, list) else [error.validator_value]
        message = '必须是' + '或'.join(names.get(kind, kind) for kind in expected) + '。'
        if isinstance(error.instance, str) and 'string' not in expected:
            message += '当前收到字符串；请直接提供对应 JSON 值。'
    elif error.validator in ('maxLength', 'minLength', 'maxItems', 'minItems', 'maximum', 'minimum'):
        message = f'不符合 {error.validator}={error.validator_value} 约束。'
    elif error.validator == 'additionalProperties' and isinstance(error.instance, dict):
        allowed = sorted(error.schema.get('properties', {}))
        message = '不接受结构以外的字段；允许字段为 ' + ', '.join(allowed) + '。'
    elif error.validator == 'required' and isinstance(error.instance, dict):
        missing = [name for name in error.validator_value if name not in error.instance]
        message = '缺少必填字段 ' + ', '.join(missing) + '。'
    else:
        message = f'不符合 {error.validator} 约束，请按工具参数结构修正。'
    return path + ' ' + message


def model_parameters(model, *, describe=None, partial=False):
    """Inline local references without discarding constraints beside a reference."""
    return schema_parameters(model.model_json_schema(), describe=describe, partial=partial)


def schema_parameters(raw, *, describe=None, partial=False):
    """Adapt an annotated schema through the same model parameter contract."""
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
        schema_maps = {'properties', 'patternProperties', 'dependentSchemas', 'dependencies'}
        schema_values = {'items', 'contains', 'additionalProperties', 'additionalItems', 'propertyNames', 'not', 'if', 'then', 'else', 'unevaluatedProperties', 'unevaluatedItems'}
        schema_arrays = {'allOf', 'anyOf', 'oneOf', 'prefixItems'}
        result = {}
        for key, item in value.items():
            if key in ('$defs', 'title'):
                continue
            if key in schema_maps:
                result[key] = {name: expand(prop, stack) if isinstance(prop, (dict, bool)) else deepcopy(prop) for name, prop in item.items()}
            elif key in schema_values:
                result[key] = expand(item, stack)
            elif key in schema_arrays:
                result[key] = [expand(prop, stack) for prop in item]
            else:
                result[key] = deepcopy(item)
        choices = result.get('anyOf', [])
        non_null = [choice for choice in choices if choice != {'type': 'null'}]
        if (len(choices) == 2 and len(non_null) == 1 and isinstance(non_null[0].get('type'), str)
                and not any(key in non_null[0] for key in ('anyOf', 'oneOf', 'allOf', 'const', 'not'))):
            # A simple nullable type can use JSON Schema's direct type union.
            # This preserves validation while keeping the value shape explicit.
            branch = non_null[0]
            outer = {key: item for key, item in result.items() if key != 'anyOf'}
            if not any(key in outer and outer[key] != value for key, value in branch.items() if key not in annotations and key != 'type'):
                result = {**branch, **outer, 'type': [branch['type'], 'null']}
                if 'enum' in branch:
                    result['enum'] = [*branch['enum'], None]
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
