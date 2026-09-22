"""Deterministic, readable Markdown from the actual business change ledger."""
import json
import re

from backend.app.schemas.body_metric import CATALOG, MEALS, STAGES
from backend.app.schemas.medical_history import MEDICAL_HISTORY_FIELDS
from backend.app.schemas.report import REPORT_STRUCTURES

NAMES = {
    'report_body': '医疗报告正文',
    'report_name': '医疗报告名称', 'report_type': '医疗报告类型', 'report_time': '就诊时间',
    'institution_name': '就诊机构', 'analysis_content': '解读结果',
    'analysis_outdated': '解读结果是否过期', 'analysis_updated_at': '解读结果更新时间',
    'item_name_zh': '检验指标名称', 'category_name': '检验分类', 'result_text': '检验结果',
    'reference_text': '参考范围', 'flag_text': '异常标记', 'aliases': '其他名称',
    'title': '标题', 'content': '正文', 'recorded_on': '记录日期',
    'member_name': '成员名称', 'relationship': '关系', 'sex': '性别', 'birth_date': '出生日期', 'blood_type': '血型',
    'notes': '备注', 'generic_name': '药品通用名', 'brand_name': '商品名',
    'strength': '规格', 'package_specification': '包装规格', 'route': '给药途径',
    'dose_text': '每次用量', 'quantity': '库存数量', 'expires_on': '有效期',
    'starts_at': '开始时间', 'ends_at': '结束时间', 'start_precision': '开始时间精度',
    'end_precision': '结束时间精度', 'timezone': '时区', 'usage_status': '用药状态',
    'prescription_type': '处方类型', 'leaflet_url': '说明书链接', 'schedule': '用药安排',
    'kind': '记录类型', 'times': '用药时间', 'time': '用药时间', 'times_per_day': '每日次数',
    'weekdays': '用药星期', 'interval_days': '间隔天数', 'anchor_date': '起算日期',
    'metric': '身体指标', 'precision': '时间精度', 'source': '数据来源', 'device': '设备', 'origin': '记录方式',
    'value': '测量值', 'secondary_value': '舒张压', 'pulse': '脉搏', 'unit': '单位',
    'method': '测量方法', 'context': '测量条件', 'basis': '依据', 'meal_type': '餐次',
    'energy': '能量（kcal）', 'carbohydrate': '碳水化合物（g）', 'protein': '蛋白质（g）', 'fat': '脂肪（g）',
    'estimated': '是否估算', 'name': '名称', 'amount': '食物数量', 'amount_unit': '食物数量单位',
    'score': '睡眠评分', 'score_max': '评分满分', 'score_basis': '评分依据', 'score_stale': '评分是否过期',
    'duration_minutes': '持续时间（分钟）', 'stage': '睡眠阶段', 'original_stage': '原始睡眠阶段',
    'activity': '运动项目', 'distance_km': '距离（km）',
    'filename': '文件名', 'original_filename': '原文件名', 'mime_type': '文件类型',
    'size_bytes': '文件大小（字节）', 'sha256': '文件摘要', 'relative_path': '文件位置',
    'source_index': '原件顺序', 'purpose': '原件用途', 'is_primary': '是否主要来源',
    'source_type': '来源类型', 'source_kind': '来源类型', 'source_value': '来源内容',
    'description': '说明', 'medication_id': '药品标识', 'record_id': '记录标识',
    'food_id': '食物标识', 'stage_id': '睡眠阶段标识', 'external_id': '外部记录标识',
    **{name: value[0] for name, value in MEDICAL_HISTORY_FIELDS.items()},
}
for _table, _model in REPORT_STRUCTURES.values():
    NAMES.update({name: field.title for name, field in _model.model_fields.items() if field.title})

KINDS = {'report': '医疗报告', 'medical_log': '健康日记', 'member': '成员基本信息',
    'medical_history': '既往史', 'medication': '药品资料', 'medication_plan': '用药计划',
    'medication_batch': '药品批次', 'body_record': '身体指标记录', 'report_source': '医疗报告来源',
    'medication_source': '药品原件', 'body_file': '身体指标附件'}
BODY_KINDS = {'measurement': '身体指标测量', 'meal': '饮食记录', 'sleep': '睡眠记录', 'workout': '运动记录'}
ENUMS = {
    'sex': {'male': '男', 'female': '女', 'other': '其他'},
    'blood_type': {'a': 'A 型', 'b': 'B 型', 'ab': 'AB 型', 'o': 'O 型', 'other': '其他'},
    'usage_status': {'taking': '正在使用', 'paused': '已暂停', 'stopped': '已停止', 'completed': '已完成', 'unknown': '未知'},
    'prescription_type': {'prescription': '处方药', 'nonprescription': '非处方药', 'unknown': '未知'},
    'kind': {**BODY_KINDS, 'daily': '每天', 'weekly': '每周', 'every_n_days': '每隔指定天数', 'as_needed': '按需使用'},
    'precision': {'instant': '时刻', 'interval': '时间区间', 'day': '日期'},
    'start_precision': {'date': '日期', 'minute': '分钟'}, 'end_precision': {'date': '日期', 'minute': '分钟'},
    'origin': {'manual': '手工记录', 'apple_health': 'Apple 健康', 'standard': '文件导入', 'image': '图片', 'demo': '示例数据'},
    'ends_at': {'long_term': '长期使用'}, 'meal_type': MEALS, 'stage': STAGES,
    'metric': {key: item['label'] for key, item in CATALOG.items()},
    'method': {'unknown': '未知'},
}
# These fields identify storage objects; their exact paths remain in evidence
# references. They do not describe health facts in the reading document.
IDENTIFIERS = frozenset({'medication_id', 'record_id', 'food_id', 'stage_id', 'external_id'})


def heading(value):
    """Keep user-supplied names on one heading line without Markdown syntax."""
    return re.sub(r'([\\`*_{}\[\]<>#!|])', r'\\\1', str(value).replace('\r', ' ').replace('\n', ' '))


def list_item(content, label=''):
    prefix = f'{heading(label)}：' if label else ''
    if '\n' in content or re.match(r'^(?:[-+*] |\d+[.)] |#{1,6} |>|```|~~~)', content):
        body = '\n'.join('  ' + line if line else '' for line in content.split('\n'))
        return f'- {prefix}\n\n{body}' if prefix else '- ' + content.replace('\n', '\n  ')
    return f'- {prefix}{content}'


def value_text(value, key=''):
    if value is None:
        return '未填写（空值）。'
    if value == '':
        return '已保存为空文本。'
    if key in {'analysis_outdated', 'is_primary'} and type(value) in (int, bool):
        return '是' if value else '否'
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, str):
        return ENUMS.get(key, {}).get(value, value)
    if isinstance(value, list):
        return '\n'.join(list_item(value_text(item, key)) for item in value) if value else '列表为空。'
    if isinstance(value, dict):
        return '\n'.join(list_item(value_text(item, name), NAMES[name])
            for name, item in value.items()) if value else '没有填写内容。'
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


def source_title(change):
    values = {field['field_path']: field['after_value'] for field in change.get('fields', []) if field['after_exists']}
    context = change.get('context', {})
    title = values.get('/report_name') or values.get('/title') or context.get('report_name') or context.get('title')
    if title:
        return str(title)
    kind = change['resource_type']
    if kind == 'body_record':
        metric = values.get('/metric') or context.get('metric')
        return CATALOG[metric]['label'] if metric in CATALOG else BODY_KINDS.get(values.get('/kind') or context.get('kind'), KINDS[kind])
    return KINDS.get(kind, '业务记录')


def source_markdown(change):
    return source_document(change)['text']


def source_document(change):
    """Render selected fields only; callers decide the authorized content scope."""
    fields = change['fields']
    if not fields:
        return {'text': '', 'units': []}
    current = {field['field_path']: field for field in fields}
    context = change.get('context', {})
    kind = change['resource_type']
    operation = change.get('operation_kind', 'create')
    lines = [f'# {heading(source_title(change))}']
    if context.get('member_name') and '/member_name' not in current:
        lines.append(list_item(str(context['member_name']), '成员'))
    identity = context.get('medication_identity') or {}
    if identity:
        lines.append('## 药品\n\n' + value_text(identity))
    # Context comes from the same saved change, never today's business object.
    context_lines = []
    for key in ('recorded_on', 'report_time', 'starts_at', 'ends_at'):
        if key in context and context[key] is not None and '/' + key not in current:
            context_lines.append(list_item(value_text(context[key], key), NAMES[key]))
    if context_lines:
        lines.append('## 资料时间\n\n' + '\n'.join(context_lines))

    groups = {}
    items = []
    item_kinds = []
    for path, field in current.items():
        parts = [part.replace('~1', '/').replace('~0', '~') for part in path.split('/')[1:]]
        key = parts[-1]
        if key in IDENTIFIERS:
            continue
        group, label = '', NAMES.get(key)
        if len(parts) >= 3 and parts[0] == 'lab_test_results':
            if key == 'category_name':
                continue
            prefix = path.rsplit('/', 1)[0]
            name = current.get(prefix + '/item_name_zh')
            name = name['after_value'] if name and name['after_exists'] else change.get('subject_names', {}).get(prefix + '/item_name_zh')
            group = prefix
            name_field = current.get(prefix + '/item_name_zh')
            if name_field and not name_field['after_exists']:
                if group not in groups:
                    groups[group] = (str(name or '检验指标') + '已删除', [])
                continue
            groups.setdefault(group, (str(name or '检验指标（名称未提供）'), []))
        elif len(parts) >= 4 and parts[:2] in (['data', 'foods'], ['data', 'stages']):
            prefix = '/'.join(path.split('/')[:-1])
            name_key = 'name' if parts[1] == 'foods' else 'stage'
            name_field = current.get(prefix + '/' + name_key)
            name = name_field['after_value'] if name_field and name_field['after_exists'] else change.get('subject_names', {}).get(prefix + '/' + name_key)
            group = prefix
            unit = change.get('subject_names', {}).get(prefix + '/amount_unit')
            if key == 'amount' and unit and prefix + '/amount_unit' not in current:
                label = f'食物数量（{unit}）'
            groups.setdefault(group, (value_text(name, name_key) if name else ('食物' if parts[1] == 'foods' else '睡眠阶段'), []))
        elif len(parts) >= 4 and parts[:2] == ['data', 'metrics']:
            metric = parts[2]
            group = '/'.join(path.split('/')[:-1])
            groups.setdefault(group, (CATALOG[metric]['label'], []))
            unit = change.get('subject_names', {}).get(group + '/unit')
            if unit and group + '/unit' not in current and key in {'value', 'secondary_value', 'pulse'}:
                label = f'{label}（{unit if key != "pulse" else "次/分"}）'
            if key == 'pulse':
                label = '脉搏（次/分）'
            if metric == 'blood_pressure' and key == 'value':
                label = '收缩压' + (f'（{unit}）' if unit and group + '/unit' not in current else '')
        elif len(parts) > 1 and parts[0] == 'schedule':
            group = '/schedule'
            groups.setdefault(group, ('用药安排', []))
            if len(parts) > 1 and parts[1] == 'kind':
                label = '用药频次'
            elif len(parts) > 2 and parts[1] == 'weekdays':
                label = '用药星期'
            elif len(parts) > 2 and parts[1] == 'times':
                label = f'用药时间 {parts[2]}'
        elif parts[0] in {'sources', 'files'}:
            label = '附件关联' + ('（主要来源）' if key == 'is_primary' else '')
        if label is None:
            # A new business field needs an explicit readable name. Never feed
            # guessed translations or internal JSON paths into model prose.
            raise ValueError(f'变更正文缺少字段名称：{kind} {path}')
        if not field['after_exists']:
            content = '此项已删除。'
        elif parts[:2] == ['schedule', 'weekdays'] and len(parts) > 2:
            content = '星期' + '一二三四五六日'[int(field['after_value']) - 1]
        else:
            content = value_text(field['after_value'], key)
        if kind == 'medical_log' and key == 'content':
            label = '日记内容'
        if kind == 'medical_log' and key == 'title':
            label = '日记标题'
        if operation == 'create' and key in {'title', 'report_name', 'item_name_zh', 'name', 'stage'} and field['after_exists'] and field['after_value']:
            continue
        if operation == 'update' and field['after_exists']:
            value = field['after_value']
            if value is None:
                content = '已清空（空值）。'
            elif value == '':
                content = '已清空（空文本）。'
            elif value == []:
                content = '已清空（空列表）。'
            elif value == {}:
                content = '已清空（空对象）。'
            else:
                # Keep the change action outside the original value, including
                # multiline Markdown and nested lists read by the stage model.
                label += '变更为'
        block = list_item(content, label)
        if group:
            groups[group][1].append(block)
        else:
            items.append(block)
            item_kinds.append('record_context' if key in {'analysis_outdated', 'analysis_updated_at'}
                or key == 'analysis_content' and field['after_exists'] and not field['after_value'] else 'text')
    item_line = len(lines)
    if items:
        lines.append('\n'.join(items))
    group_start = len(lines)
    for title, blocks in groups.values():
        lines.append(f'## {heading(title)}' + ('\n\n' + '\n'.join(blocks) if blocks else ''))
    text = '\n\n'.join(lines)
    units, offset = [], 0
    for index, line in enumerate(lines):
        end = offset + len(line) + (2 if index < len(lines) - 1 else 0)
        if items and index == item_line:
            position = offset
            for number, (item, item_kind) in enumerate(zip(items, item_kinds)):
                item_end = position + len(item) + 1 if number < len(items) - 1 else end
                units.append({'character_start': position, 'character_end': item_end, 'kind': item_kind})
                position = item_end
        else:
            units.append({'character_start': offset, 'character_end': end,
                          'kind': 'field_group' if index >= group_start else 'text'})
        offset = end
    if kind in {'medication', 'medication_plan', 'medication_batch'} or (kind == 'body_record'
            and (current.get('/kind', {}).get('after_value') or context.get('kind')) == 'measurement'):
        units = [{'character_start': 0, 'character_end': len(text), 'kind': 'field_group'}]
    return {'text': text, 'units': units}
