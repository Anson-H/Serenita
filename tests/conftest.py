import pytest


@pytest.fixture(autouse=True)
def isolated_default_data_root(tmp_path, monkeypatch):
    """Even low-level tests must never create data in the real dev account tree."""
    monkeypatch.setenv("DATA_ROOT", str(tmp_path / "default-data"))
    yield
    from backend.app.core.conversation_tasks import wait_for_all_jobs

    wait_for_all_jobs(timeout=10)
