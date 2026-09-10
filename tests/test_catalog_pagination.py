"""Directory pages cover a complete scope without loading detailed resources."""
import pytest
from tests.member_support import accounts, account_id, create_member, report_payload
from backend.app.application.report_service import ReportService
from backend.app.repositories.report_repository import ReportRepository
from backend.app.repositories.medical_log_repository import MedicalLogRepository


def test_report_catalog_pages_are_filtered_stable_and_complete(accounts, monkeypatch):
    owner, *_ = accounts
    member = create_member(owner)
    service = ReportService.for_member(account_id('owner'), member)
    expected = set()
    for index in range(29):
        report = service.repository.create_manual_report(member, {**report_payload(), 'report_name': str(index)})
        expected.add(report['report_id'])
    monkeypatch.setattr(ReportRepository, 'list_reports', lambda *a, **k: pytest.fail('catalog must not read full report list'))
    monkeypatch.setattr(ReportRepository, 'get_report_detail', lambda *a, **k: pytest.fail('catalog must not assemble details'))
    first = service.read_report_catalog(member)
    assert first['total'] == 29 and len(first['reports']) == 24 and first['next_cursor']
    # The seek cursor remains usable if its preceding row was deleted.
    service.repository.delete_report(member, first['reports'][-1]['report_id'])
    second = service.read_report_catalog(member, cursor=first['next_cursor'])
    assert second['total'] == 28 and len(second['reports']) == 5 and second['next_cursor'] is None
    assert set(first['report_ids'] + second['report_ids']) == expected
    with pytest.raises(ValueError):
        service.read_report_catalog(member, cursor=first['next_cursor'], before_date='2026-01-01')
    assert service.read_report_catalog(member, before_date='2026-01-01')['total'] == 0
    with pytest.raises(ValueError):
        service.read_report_catalog(member, limit=101)


def test_log_pages_bound_content_and_do_not_join_report_store(accounts, monkeypatch):
    owner, *_ = accounts
    member = create_member(owner)
    path = f'/api/members/{member}/medical-logs'
    expected = set()
    for index in range(31):
        result = owner.post(path, json={'recorded_on': '2026-09-01', 'title': f'日志 {index}', 'content': '一' * 5000})
        assert result.status_code == 201
        expected.add(result.json()['medical_log']['medical_log_id'])
    monkeypatch.setattr(ReportRepository, 'init_db', lambda *a: pytest.fail('catalog must not open report store'))
    monkeypatch.setattr(MedicalLogRepository, '_detail', lambda *a: pytest.fail('catalog must not assemble detail'))
    first = owner.get(path).json()
    assert first['total'] == 31 and len(first['medical_logs']) == 24
    assert all(len(item['summary']) <= 121 and 'content' not in item for item in first['medical_logs'])
    second = owner.get(path, params={'cursor': first['next_cursor']}).json()
    assert len(second['medical_logs']) == 7 and second['next_cursor'] is None
    assert {item['medical_log_id'] for item in first['medical_logs'] + second['medical_logs']} == expected
    assert owner.get(path, params={'cursor': first['next_cursor'], 'query': 'different'}).status_code == 400
    assert owner.get(path, params={'limit': 101}).status_code == 400
