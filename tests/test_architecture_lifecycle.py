"""Regression coverage for authorization and background execution boundaries."""
from contextlib import contextmanager
import threading
from types import SimpleNamespace

import pytest

from backend.app.application.auth_service import AuthService, AuthServiceError
from backend.app.application.conversations.jobs import ConversationTurnJobs
from backend.app.application.model_settings_service import _probe_metadata_baseline
from backend.app.agent_runtime.model_types import AssistantModelOutput
from backend.app.domain.model_capabilities import ModelCapabilityProfile, ModelCapabilityProfiles, ModelModeCapabilityProfile, profiles_from_profile
from backend.app.providers.base import ModelProvider
from backend.app.providers.types import ProviderModel
from backend.app.repositories.conversation_repository import ConversationRepository
from backend.app.storage.sqlite import connect


def account():
    auth = AuthService()
    user, token = auth.sign_up(account="audit", account_name="audit", password="old", confirm_password="old")
    return auth, user, token


def test_password_change_between_verification_and_session_issue(monkeypatch):
    auth, user, _ = account()
    issue = auth.repository.create_session
    def interleaved(**values):
        auth.change_password(user=user, current_password="old", new_password="new", confirm_password="new")
        return issue(**values)
    monkeypatch.setattr(auth.repository, "create_session", interleaved)
    with pytest.raises(AuthServiceError) as error:
        auth.sign_in(account="audit", password="old")
    assert error.value.code == "SIGN_IN_FAILED"
    with connect(auth.paths.auth_db) as db:
        assert db.execute("SELECT count(*) FROM login_sessions").fetchone()[0] == 1
    monkeypatch.setattr(auth.repository, "create_session", issue)
    new_user, token = auth.sign_in(account="audit", password="new")
    assert auth.current_user(token).account_id == new_user.account_id


@pytest.mark.parametrize("stage", ["messages", "title"])
def test_job_initialization_failure_releases_heartbeat_and_registry(stage):
    turn = {"turn_id": "init", "stream_id": "stream", "session_id": "session", "user_message_id": "user", "status": "queued"}
    state = SimpleNamespace(lock=threading.RLock(), threads={}, cancellations={})
    touched, failures, promoted = [], [], []
    def fail():
        raise OSError("initialization failed")
    repo = SimpleNamespace(
        turn_by_stream_id=lambda *args: turn,
        claim_turn_job=lambda *args: turn.update(status="streaming") or True,
        touch_turn_job=lambda *args: touched.append(args),
        messages_by_id=lambda *args: fail() if stage == "messages" else {},
    )
    jobs = ConversationTurnJobs(repo, state, SimpleNamespace(start=lambda *args: fail()),
        execute_turn=lambda *args, **kwargs: pytest.fail("execution must not start"),
        record_failure=lambda *args: failures.append(args),
        promote_next=lambda *args: promoted.append(args))
    jobs.start("actor", "session", "stream")
    jobs.wait("actor", "session", "stream", timeout=3)
    assert not state.threads and not state.cancellations
    assert len(failures) == len(promoted) == 1
    assert failures[0][2] == "TURN_JOB_FAILED"
    assert not any(t.name == "serenita-turn-heartbeat-init" and t.is_alive() for t in threading.enumerate())


@pytest.mark.parametrize("intervening", ["heartbeat", "cancel"])
def test_lease_update_rechecks_current_state_at_write(monkeypatch, intervening):
    auth, user, _ = account()
    repo = ConversationRepository(paths=auth.paths)
    session = repo.ensure_session(user.account_id, member_id=None)
    repo.insert_turn(user.account_id, session, "turn", "user", None, "stream", "streaming", None, None, "2000-01-01", "2000-01-01")
    from backend.app.repositories import turn_index
    invoked = []
    @contextmanager
    def interleaved(path):
        class Connection:
            def execute(self, sql, args=()):
                if not invoked and ("SELECT * FROM conversation_turns" in sql or "UPDATE conversation_turns" in sql):
                    invoked.append(True)
                    with connect(path) as writer:
                        if intervening == "heartbeat":
                            writer.execute("UPDATE conversation_turns SET updated_at='2030-01-01'")
                        else:
                            writer.execute("UPDATE conversation_turns SET status='cancelled'")
                return db.execute(sql, args)
        with connect(path) as db:
            yield Connection()
    monkeypatch.setattr(turn_index, "connect", interleaved)
    assert repo.expire_turn_jobs(user.account_id, session, "2020-01-01") == []
    assert repo.turn_row(user.account_id, session, "turn")["status"] == ("streaming" if intervening == "heartbeat" else "cancelled")


def test_metadata_without_declarations_preserves_each_thinking_state():
    current = ModelCapabilityProfiles(
        non_thinking=ModelModeCapabilityProfile(availability="available", supports_text=True, file_mime_types=["image/png"], supports_tool_calling=True),
        thinking=ModelModeCapabilityProfile(availability="available", supports_text=True),
    )
    aggregate = ModelCapabilityProfile(file_mime_types=["image/png"], supports_tool_calling=True, thinking_modes=["off", "high"])
    _, profiles, _, declarations = _probe_metadata_baseline(
        remote_model=ProviderModel(remote_model_id="model", model_name="model"), metadata_result={},
        current_profile=aggregate, current_profiles=current)
    assert profiles == current
    assert declarations == {}


@pytest.mark.parametrize("terminal", ["completed", "cancelled"])
def test_expiry_waits_for_session_terminal_publication(monkeypatch, terminal):
    from backend.app.application.conversations.service import ConversationService

    auth, user, _ = account()
    service = ConversationService(paths=auth.paths)
    repo = service.repository
    session = repo.ensure_session(user.account_id, member_id=None)
    repo.insert_turn(user.account_id, session, "turn", "user", None, "stream", "streaming", None, None, "2000-01-01", "2000-01-01")
    located, write_attempted = threading.Event(), threading.Event()
    errors = []
    locate, expire = repo.expired_turn_job_sessions, repo.expire_turn_jobs

    def locate_sessions(*args):
        result = locate(*args)
        located.set()
        return result

    def expire_session(*args):
        write_attempted.set()
        return expire(*args)

    def interrupt():
        try:
            service.lifecycle.interrupt_expired_turn_jobs(user.account_id)
        except Exception as exc:
            errors.append(exc)

    monkeypatch.setattr(repo, "expired_turn_job_sessions", locate_sessions)
    monkeypatch.setattr(repo, "expire_turn_jobs", expire_session)
    worker = threading.Thread(target=interrupt)
    with service.task_state.session_lock(user.account_id, session):
        worker.start()
        assert located.wait(3)
        assert not write_attempted.wait(.1)
        if terminal == "completed":
            repo.update_turn_completed(user.account_id, session, "turn", None)
        else:
            repo.update_turn_cancelled(user.account_id, session, "turn", None)
    worker.join(3)
    assert not worker.is_alive() and not errors
    assert write_attempted.is_set()
    assert repo.turn_row(user.account_id, session, "turn")["status"] == terminal
    assert not list(service.events.view(user.account_id, session).events)


def test_expiry_ends_only_expired_workers_in_each_locked_session():
    from backend.app.application.conversations.service import ConversationService

    auth, user, _ = account()
    service = ConversationService(paths=auth.paths)
    repo = service.repository
    sessions = [repo.ensure_session(user.account_id, member_id=None) for _ in range(2)]
    for session in sessions:
        repo.insert_turn(user.account_id, session, "turn", "user", None, "stream", "streaming", None, None, "2000-01-01", "2000-01-01")
    repo.touch_turn_job(user.account_id, sessions[1], "turn")
    service.lifecycle.interrupt_expired_turn_jobs(user.account_id)
    assert repo.turn_row(user.account_id, sessions[0], "turn")["status"] == "failed"
    assert repo.turn_row(user.account_id, sessions[1], "turn")["status"] == "streaming"
    ends = [event for event in service.events.view(user.account_id, sessions[0]).events if event.type == "turn/end"]
    assert len(ends) == 1 and ends[0].data["reason"]["kind"] == "interrupted"
    assert not list(service.events.view(user.account_id, sessions[1]).events)


@pytest.mark.parametrize("terminal", ["completed", "cancelled", "expired"])
def test_late_worker_failure_waits_and_preserves_terminal(monkeypatch, terminal):
    from backend.app.application.conversations.service import ConversationService

    auth, user, _ = account()
    service = ConversationService(paths=auth.paths)
    repo = service.repository
    session = repo.ensure_session(user.account_id, member_id=None)
    repo.insert_turn(user.account_id, session, "turn", "user", None, "stream", "streaming", None, None, "2000-01-01", "2000-01-01")
    turn = repo.turn_row(user.account_id, session, "turn")
    started, appended = threading.Event(), threading.Event()
    errors = []
    append = repo.append_session_events

    def append_events(*args, **kwargs):
        appended.set()
        return append(*args, **kwargs)

    def fail():
        started.set()
        try:
            service.lifecycle.record_turn_failure(user.account_id, turn, "TURN_JOB_FAILED", "late failure")
        except Exception as exc:
            errors.append(exc)

    monkeypatch.setattr(repo, "append_session_events", append_events)
    worker = threading.Thread(target=fail)
    with service.task_state.session_lock(user.account_id, session):
        worker.start()
        assert started.wait(3)
        assert not appended.wait(.1)
        if terminal == "completed":
            repo.update_turn_completed(user.account_id, session, "turn", None)
        elif terminal == "cancelled":
            repo.update_turn_cancelled(user.account_id, session, "turn", None)
        else:
            repo.expire_turn_jobs(user.account_id, session, "2020-01-01")
    worker.join(3)
    assert not worker.is_alive() and not errors and not appended.is_set()
    current = repo.turn_row(user.account_id, session, "turn")
    assert current["status"] == ("failed" if terminal == "expired" else terminal)
    if terminal == "expired":
        assert current["error_code"] == "TURN_INTERRUPTED"


def test_worker_failure_records_one_terminal_even_when_reported_twice():
    from backend.app.application.conversations.service import ConversationService

    auth, user, _ = account()
    service = ConversationService(paths=auth.paths)
    repo = service.repository
    session = repo.ensure_session(user.account_id, member_id=None)
    repo.insert_turn(user.account_id, session, "turn", "user", None, "stream", "streaming", None, None, "2000-01-01", "2000-01-01")
    turn = repo.turn_row(user.account_id, session, "turn")
    service.lifecycle.record_turn_failure(user.account_id, turn, "MODEL_ERROR", "first failure")
    service.lifecycle.record_turn_failure(user.account_id, turn, "TURN_JOB_FAILED", "late failure")
    ends = [event for event in service.events.view(user.account_id, session).events if event.type == "turn/end"]
    assert len(ends) == 1 and ends[0].data["reason"]["code"] == "MODEL_ERROR"
    assert repo.turn_row(user.account_id, session, "turn")["error_code"] == "MODEL_ERROR"


@pytest.mark.parametrize("answer, expected", [("I cannot read this image", "unverified"), ("ok", "unverified"), ("purple", "supported")])
def test_image_probe_requires_sample_content_and_only_proves_png(answer, expected):
    class Provider(ModelProvider):
        def native_attachment_mime_types(self):
            return {"image/png", "image/jpeg", "image/heic"}
        def complete_chat(self, api_url, api_key, remote_model_id, model_request, **kwargs):
            return AssistantModelOutput(content=answer)
    result = Provider().probe_capabilities(api_url="https://example.invalid", api_key="unused", remote_model_id="test",
        current_profiles=profiles_from_profile(ModelCapabilityProfile()), thinking_modes=["default"],
        capability_declarations={"text": True, "tool_calling": False, "pdf_input": False, "audio_input": False, "video_input": False})
    assert result.checks["aggregate"]["image_input"] == expected
    assert result.profiles.non_thinking.file_mime_types == (["image/png"] if expected == "supported" else [])


def test_failed_member_session_cleanup_does_not_skip_other_tasks(monkeypatch):
    from backend.app.application.member_service import MemberService
    from backend.app.application.conversations.service import ConversationService
    auth, user, _ = account()
    conversations = ConversationService(paths=auth.paths)
    members = MemberService(conversations=conversations)
    member = members.create_member(user.account_id, {"member_name": "member"})["member_id"]
    sessions = [conversations.repository.ensure_session(user.account_id, member_id=member) for _ in range(2)]
    called = []
    def interrupt(actor, session, *, before=None):
        called.append(session)
        assert before is not None
        if session == sessions[0]:
            raise OSError("one session unavailable")
    monkeypatch.setattr(conversations, "interrupt_member_session", interrupt)
    result = members.delete_member(user.account_id, member)
    assert result["deleted"] is True
    assert set(called) == set(sessions)
    path = members.lifecycle_tasks.repository.path
    with connect(path) as db:
        pending = db.execute("SELECT * FROM member_lifecycle_tasks").fetchall()
        assert len(pending) == 1 and pending[0]["session_id"] == sessions[0]
        assert pending[0]["attempt_count"] == 1
        db.execute("UPDATE member_lifecycle_tasks SET next_attempt_at='2000-01-01'")
    monkeypatch.setattr(conversations, "interrupt_member_session", lambda actor, session, **kwargs: called.append(session))
    members.lifecycle_tasks.drain()
    with connect(path) as db:
        assert db.execute("SELECT count(*) FROM member_lifecycle_tasks").fetchone()[0] == 0
    assert called.count(sessions[0]) == 2


def test_revoking_owner_or_missing_grant_preserves_member_selection():
    from backend.app.application.member_service import MemberService
    from backend.app.core.errors import SerenitaError
    auth, user, _ = account()
    members = MemberService()
    member = members.create_member(user.account_id, {"member_name": "member"})["member_id"]
    before = members.list_members(user.account_id)
    with pytest.raises(SerenitaError) as error:
        members.revoke(user.account_id, member, user.account_id)
    assert error.value.code == "INVALID_MEMBER_GRANT"
    assert members.list_members(user.account_id) == before
    assert members.repository.revoke(user.account_id, member, "absent-account") == []
    assert members.list_members(user.account_id) == before


def test_default_eligibility_and_type_change_are_serialized(monkeypatch):
    from backend.app.application.model_settings_service import ModelSettingsService
    from backend.app.repositories.model_provider_repository import ModelProviderRepository, ModelProviderTransaction
    from backend.app.schemas.model_provider import ModelDefaultsPatchRequest, ModelPatchRequest
    auth, user, _ = account()
    repository = ModelProviderRepository(paths=auth.paths)
    with repository.transaction(user.account_id, write=True) as tx:
        tx.save_provider(provider_id="test", provider_name="test", api_url="https://example.invalid", official_url=None,
            encrypted_api_key=None, is_configured=0, created_at="2026-01-01", updated_at="2026-01-01")
        tx.save_model(model_id="test:model", provider_id="test", remote_model_id="model", model_name="model", created_at="2026-01-01", updated_at="2026-01-01")
        profile = ModelCapabilityProfile()
        tx.write_typed_model(model_id="test:model", model_type="generation", model_name="model", profile=profile,
            profiles=profiles_from_profile(profile), updated_at="2026-01-01")
    service = ModelSettingsService(repository=repository)
    read, release, writer_started, writer_done = (threading.Event() for _ in range(4))
    errors = []
    get = ModelProviderTransaction.get_model
    def pause(tx, **kwargs):
        result = get(tx, **kwargs)
        if threading.current_thread().name == "default-reader":
            read.set()
            assert release.wait(3)
        return result
    monkeypatch.setattr(ModelProviderTransaction, "get_model", pause)
    def choose():
        try:
            service.update_model_defaults(user.account_id, ModelDefaultsPatchRequest(chat="test:model"))
        except Exception as error:
            errors.append(error)
    def change():
        writer_started.set()
        try:
            service.update_model(user.account_id, "test:model", ModelPatchRequest(model_type="unknown"))
        except Exception as error:
            errors.append(error)
        finally:
            writer_done.set()
    reader = threading.Thread(target=choose, name="default-reader")
    writer = threading.Thread(target=change)
    reader.start()
    assert read.wait(3)
    writer.start()
    assert writer_started.wait(3)
    try:
        assert not writer_done.wait(.15)
    finally:
        release.set()
        reader.join(4)
        writer.join(4)
    assert not reader.is_alive() and not writer.is_alive() and not errors
    assert service.list_model_defaults(user.account_id)["defaults"]["chat"] is None
    assert repository.get_model(user.account_id, "test:model")["model_type"] == "unknown"


def test_newly_available_thinking_state_does_not_borrow_unverified_media_or_tools():
    from backend.app.providers.errors import ProviderChatCompletionError
    class Provider(ModelProvider):
        def complete_chat(self, api_url, api_key, remote_model_id, model_request, **kwargs):
            if isinstance(model_request.messages[0].get("content"), list):
                raise ProviderChatCompletionError("timeout", code="MODEL_TIMEOUT")
            return AssistantModelOutput(content="ok")
    current = ModelCapabilityProfiles(
        non_thinking=ModelModeCapabilityProfile(availability="available", supports_text=True,
            file_mime_types=["image/png"], supports_tool_calling=True),
        thinking=ModelModeCapabilityProfile(availability="unavailable"),
    )
    result = Provider().probe_capabilities(api_url="https://example.invalid", api_key="unused", remote_model_id="model",
        current_profiles=current, thinking_modes=["off"], capability_declarations={})
    assert result.profiles.non_thinking.file_mime_types == ["image/png"]
    assert result.profiles.non_thinking.supports_tool_calling is True
    assert result.profiles.thinking.availability == "available"
    assert result.profiles.thinking.file_mime_types == []
    assert result.profiles.thinking.supports_tool_calling is False
    assert result.checks["thinking"]["image_input"] == "unverified"
    assert result.checks["thinking"]["tool_calling"] == "unverified"
