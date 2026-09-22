"""Load each background stage's prompt and model contract from one YAML file."""
from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
from string import Formatter

import yaml
from jsonschema import Draft202012Validator

from backend.app.core.time import local_now, local_timezone_name


PROMPT_ROOT = Path(__file__).parents[2] / 'plugins/memory/prompts'


class ConfigLoader(yaml.CSafeLoader):
    """Reject duplicate YAML keys instead of silently replacing a contract."""


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise ValueError(f'Duplicate memory prompt key: {key}')
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


ConfigLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


@dataclass(frozen=True)
class MemoryPromptConfig:
    name: str
    values: dict
    common_rules: str

    @classmethod
    def load(cls, name, *, root=PROMPT_ROOT):
        document = yaml.load((root / f'{name}.yaml').read_text(encoding='utf-8'), Loader=ConfigLoader)
        if not isinstance(document, dict) or set(document) != {name}:
            raise ValueError(f'Memory prompt must have exactly one stage root: {name}')
        values = document[name]
        required = {'description', 'version', 'variables', 'template', 'input_schema', 'output_schema', 'definitions'}
        optional = {'strict_requirements', 'custom_background', 'custom_requirements'}
        if not isinstance(values, dict) or not required <= set(values) or set(values) - required - optional:
            raise ValueError(f'Memory prompt config fields do not match: {name}')
        declared = values['variables']
        fields = {field for _, field, _, _ in Formatter().parse(values['template']) if field is not None}
        if not isinstance(declared, list) or len(set(declared)) != len(declared) or fields != set(declared):
            raise ValueError(f'Memory prompt variables do not match the template: {name}')
        if fields - {'time', 'timezone', 'common_rules', 'custom_background', 'custom_requirements'}:
            raise ValueError(f'Unsupported memory prompt variables: {name}')
        sections = [f'## {title}' for title in ('Role', 'Background', 'Task', 'Input', 'Output', 'Rules')]
        positions = [values['template'].find(section) for section in sections]
        if any(position < 0 for position in positions) or positions != sorted(positions):
            raise ValueError(f'Memory prompt requires the six ordered sections: {name}')
        common = yaml.load((root / 'common.yaml').read_text(encoding='utf-8'), Loader=ConfigLoader)
        config = cls(name, values, common['common']['rules'])
        for kind in ('input', 'output'):
            Draft202012Validator.check_schema(config.schema(kind))
        return config

    def schema(self, kind):
        schema = deepcopy(self.values[f'{kind}_schema'])
        schema['definitions'] = deepcopy(self.values['definitions'])
        return schema

    def extraction_requirements(self):
        """Combine shared evidence rules with the extraction stage context."""
        return "\n\n".join(part.strip() for part in (
            self.common_rules, self.values.get("custom_requirements", "")) if part.strip())

    def prompt(self):
        text = self.values['template'].format(time=local_now().strftime('%Y-%m-%d %H:%M'),
            timezone=local_timezone_name(), common_rules=self.common_rules,
            custom_background=self.values.get('custom_background', ''),
            custom_requirements=self.extraction_requirements())
        return text + '\n\n输出 Schema：\n' + json.dumps(self.schema('output'), ensure_ascii=False, separators=(',', ':'))

    def validate_input(self, values):
        Draft202012Validator(self.schema('input')).validate(values)
