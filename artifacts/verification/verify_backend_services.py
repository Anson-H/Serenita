"""Read-only product checks and explicitly authorized live provider acceptance.

Run with --base-url pointing at the real managed backend. Uses the preserved local
admin account and saved configuration. Writes only a credential-free acceptance
report; model inputs contain generated test text or the built-in probe image.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import httpx
from backend.app.application.services import ApplicationServices
from backend.app.agent_runtime.model_types import ModelRequest
from backend.app.core.cancellation import CancellationToken
from backend.app.core.time import local_now_iso
from backend.app.storage.model_codec import model_response
from backend.app.storage.sqlite import connect


def fingerprint_settings(path):
    with connect(path) as connection:
        tables = [row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        rows = {table: sorted([list(row) for row in connection.execute('SELECT * FROM "' + table.replace('"', '""') + '"')], key=repr) for table in tables}
    encoded = json.dumps(rows, sort_keys=True, default=lambda value: value.hex() if isinstance(value, bytes) else str(value)).encode()
    return hashlib.sha256(encoded).hexdigest()


def run(base_url):
    services = ApplicationServices()
    account = services.auth.repository.account_by_login('admin')
    assert account is not None and account['account_name'] == 'serenita'
    account_id = account['account_id']
    original_account = tuple(account[key] for key in ('account_id', 'account', 'account_name', 'password_hash'))
    config_before = fingerprint_settings(services.paths.config_db(account_id))
    key_paths = [services.paths.provider_master_key, services.paths.web_access_master_key]
    keys_before = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in key_paths}
    report = {'started_at': local_now_iso(), 'base_url': base_url, 'data_root': str(services.paths.root), 'checks': [], 'external_requests': []}
    output = ROOT / 'artifacts/verification/real-service-acceptance.json'

    def record(name, status, **details):
        item = {'name': name, 'status': status, **details}
        report['checks'].append(item)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(item, ensure_ascii=False), flush=True)

    def failure(exc):
        detail = getattr(exc, 'detail', {})
        return {'error_type': type(exc).__name__, 'error_code': detail.get('code', getattr(exc, 'code', None)),
                'message': detail.get('message', str(exc))[:500]}

    with httpx.Client(base_url=base_url, timeout=20, trust_env=False) as client:
        response = client.post('/api/auth/sign_in', json={'account': 'admin', 'password': '123456'})
        response.raise_for_status()
        assert response.json()['account_id'] == account_id
        record('真实开发账号登录', 'passed')
        for path in ['/api/auth/session', '/api/members', '/api/conversations', '/api/favorites', '/api/model-providers', '/api/models', '/api/model-access-settings', '/api/account-settings/web-access']:
            result = client.get(path)
            record('HTTP ' + path, 'passed' if result.status_code == 200 else 'failed', http_status=result.status_code)

    with services.model_settings.repository.transaction(account_id) as transaction:
        models = [model_response(row) for row in transaction.list_models()]
    defaults = {purpose: services.models.default_model_for_account(account_id, purpose) for purpose in ('chat', 'compact', 'title', 'vision_parse')}
    image = base64.b64encode((ROOT / 'backend/app/providers/probe_assets/image.png').read_bytes()).decode('ascii')
    jobs = [(f'默认用途 {purpose}', model, purpose, purpose == 'vision_parse') for purpose, model in defaults.items()]
    default_model_ids = {model['model_id'] for model in defaults.values() if model}
    jobs.extend((f'已配置模型 {model["model_id"]}', model, 'chat', 'vision' in model['remote_model_id']) for model in models if model['model_id'] not in default_model_ids)
    original_send = httpx.Client.send

    def counted_send(client, request, *args, **kwargs):
        report['external_requests'].append({'method': request.method, 'host': request.url.host, 'path': request.url.path})
        return original_send(client, request, *args, **kwargs)

    with patch.object(httpx.Client, 'send', counted_send):
        for label, model, purpose, vision in jobs:
            started = time.monotonic()
            count_before = len(report['external_requests'])
            if model is None:
                record(label, 'failed', message='默认用途未配置模型')
                continue
            try:
                content = '仅回复 OK。'
                if vision:
                    content = [{'type': 'text', 'text': '请用一句话描述图片。'}, {'type': 'image', 'mime_type': 'image/png', 'data_base64': image}]
                request = ModelRequest.build(system='', messages=[{'role': 'user', 'content': content}], model_config={'max_output_tokens': 128, 'purpose': purpose})
                mode = 'off' if 'off' in model['thinking_modes'] else 'default'
                if purpose == 'chat' and model['model_id'] == defaults['chat']['model_id']:
                    prepared = services.models.prepare_stream_chat_for_account(account_id=account_id, model=model, model_request=request, thinking_mode=mode)
                    chunks = list(services.models.stream_prepared_chat_for_account(prepared_request=prepared, timeout_seconds=60, cancellation_token=CancellationToken()))
                    text = ''.join(chunk.content_delta or '' for chunk in chunks)
                    usage = next((chunk.usage for chunk in reversed(chunks) if chunk.usage), {})
                else:
                    result = services.models.complete_chat_for_account(account_id=account_id, model=model, model_request=request, thinking_mode=mode, timeout_seconds=60, cancellation_token=CancellationToken())
                    text, usage = result.content, result.usage
                assert text.strip(), '模型未返回正文'
                record(label, 'passed', model_id=model['model_id'], provider_id=model['provider_id'], vision=vision,
                       response_characters=len(text), usage=usage, request_count=len(report['external_requests'])-count_before,
                       elapsed_seconds=round(time.monotonic()-started, 2))
            except Exception as exc:
                record(label, 'failed', model_id=model['model_id'], request_count=len(report['external_requests'])-count_before,
                       elapsed_seconds=round(time.monotonic()-started, 2), **failure(exc))
        try:
            search = services.web.search(account_id, query='World Health Organization official website', include_domains=['who.int'])
            assert search['provider'] == 'exa' and search['results']
            record('Exa 搜索', 'passed', result_count=len(search['results']))
            read_service = services.web.for_runtime(lambda **scope: {'output': search} if scope['call_id']=='acceptance-search' and scope['session_id']=='acceptance-session' else None)
            page = read_service.read(account_id, search_call_id='acceptance-search', result_index=search['results'][0]['result_index'], mode='full', session_id='acceptance-session', visible_message_ids=['acceptance-message'])
            assert page['total_characters'] > 0
            assert page['pages'][0]['citation_id'] == search['results'][0]['citation_id']
            record('Exa 网页正文', 'passed', total_characters=page['total_characters'], pages=len(page['pages']), url=page['pages'][0]['url'])
        except Exception as exc:
            record('Exa 实际调用', 'failed', **failure(exc))
    tavily = next(provider for provider in services.web.settings(account_id)['providers'] if provider['provider_id']=='tavily')
    record('Tavily 真实服务', 'not_applicable' if not tavily['has_api_key'] else 'pending', reason='无配置凭证，模拟适配器已由后端测试覆盖')
    current = services.auth.repository.account_by_login('admin')
    preserved = (original_account == tuple(current[key] for key in ('account_id', 'account', 'account_name', 'password_hash'))
                 and config_before == fingerprint_settings(services.paths.config_db(account_id))
                 and keys_before == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in key_paths})
    record('账号身份、全部配置及配套主密钥保留', 'passed' if preserved else 'failed')
    report['finished_at'] = local_now_iso()
    report['external_request_count'] = len(report['external_requests'])
    report['status'] = 'passed' if all(item['status'] in {'passed', 'not_applicable'} for item in report['checks']) else 'incomplete'
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    return 0 if report['status']=='passed' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--base-url', required=True)
    raise SystemExit(run(parser.parse_args().base_url))
