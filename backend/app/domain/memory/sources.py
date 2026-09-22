"""Registered health archive sources and default memory control scope."""
from dataclasses import dataclass

@dataclass(frozen=True)
class SourceRegistration:
    database: str
    categories: frozenset[str]
    scope: str
    table: str | None = None
    primary_key: str | None = None


def registered(database, category, scope, table=None, primary_key=None):
    categories = frozenset(category if isinstance(category, tuple) else (category,))
    return SourceRegistration(database, categories, scope, table, primary_key)


SOURCE_REGISTRATIONS = {
    "member": registered("members.db", "member_profile", "member", "members", "member_id"),
    "medical_history": registered("members.db", "member_profile", "member", "medical_history", "member_id"),
    "report": registered("reports.db", "medical_report", "member", "reports", "report_id"),
    "report_source": registered("reports.db", "medical_report", "member", "report_sources", "resource_id"),
    "medical_log": registered("medical_logs.db", "medical_log", "member", "medical_logs", "medical_log_id"),
    "medication": registered("medications.db", "medication", "catalog", "medications", "medication_id"),
    "medication_source": registered("medications.db", "medication", "catalog", "medication_sources", "resource_id"),
    "medication_plan": registered("medications.db", "medication", "member", "medication_plans", "medication_plan_id"),
    "medication_batch": registered("medications.db", "medication", "member", "medication_inventory", "medication_batch_id"),
    "body_record": registered("body_metrics.db", "body_metric", "member", "body_records", "record_id"),
    "body_file": registered("body_metrics.db", "body_metric", "member", "body_files", "file_id"),
}


BUSINESS_SOURCE_DATABASES = tuple(dict.fromkeys(item.database for item in SOURCE_REGISTRATIONS.values()))


def default_memory_settings(access):

    return {
        "member_id": access.member_id, "setting_id": None, "formation_state": "enabled",
        "source_categories": list(dict.fromkeys(category for registration in SOURCE_REGISTRATIONS.values() for category in registration.categories)), "embedding_model_id": None,
        "effective_at": None,
    }
