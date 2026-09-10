from __future__ import annotations
from backend.app.plugins.web.registry import build_tools
import json
import re
import sqlite3
import tempfile
from pathlib import Path
from types import SimpleNamespace
import httpx
from member_support import account_id as account_id_for
import pytest
from tests.api_client import TestClient
from backend.app.agent_runtime.model_types import ModelRequest, ToolSchema
from backend.app.plugins import PluginRuntimeContext, build_builtin_skills
from backend.app.application.model_provider_service import ModelProviderService
from backend.app.plugins.web.adapters import ExaAdapter, TavilyAdapter, WebProviderAdapter
from backend.app.plugins.web.citations import export_web_citation_markdown, web_citation_sources_from_events
from backend.app.plugins.web.errors import WebAccessError
from backend.app.plugins.web.service import WebAccessService
from backend.app.core.tabular_json import encode_tabular_json
from backend.app.repositories.web_access_repository import WebAccessRepository
from backend.app.storage.paths import app_paths


@pytest.fixture
def isolated_data_root(monkeypatch):
    with tempfile.TemporaryDirectory() as directory:
        monkeypatch.setenv("DATA_ROOT", directory)
        monkeypatch.delenv("WEB_ACCESS_MASTER_KEY", raising=False)
        yield Path(directory)


def _json_response(payload, status=200, headers=None):
    return httpx.Response(
        status,
        json=payload,
        headers=headers,
    )


def test_web_plugin_has_no_skills_and_exposes_only_direct_tools():
    before = {skill.name for skill in build_builtin_skills()}
    tools = build_tools(
        runtime_context=PluginRuntimeContext(
            account_id=account_id_for("alice"),
            event_recorder=lambda _event: None,
        ),
    )

    assert before
    assert {skill.name for skill in build_builtin_skills()} == before
    assert {tool.name for tool in tools} == {"web_search", "web_read"}
    assert {tool.model_exposure for tool in tools} == {"direct"}
    assert all("api_key" not in json.dumps(tool.input_schema) for tool in tools)
    by_name = {tool.name: tool for tool in tools}
    assert "url" not in by_name["web_read"].input_schema["properties"]
    assert "max_results" not in by_name["web_search"].input_schema["properties"]
    assert "cursor" not in by_name["web_search"].input_schema["properties"]
    assert "page_size" not in by_name["web_search"].input_schema["properties"]
    assert "result_indexes" not in by_name["web_read"].input_schema["properties"]
    assert "result_index" in by_name["web_read"].input_schema["properties"]
    assert "cursor" not in by_name["web_read"].input_schema["properties"]
    assert "page_size" not in by_name["web_read"].input_schema["properties"]


def test_web_citations_project_from_tool_results_without_rewriting_raw_content():
    raw_content = (
        "结论一。[cite:abc-1] 未知来源。[cite:missing] "
        "`示例 [cite:abc-1]`\\[cite:literal]"
    )
    search_output = encode_tabular_json(
        {
            "results": [
                {
                    "citation_id": "abc-1",
                    "title": "WHO [guidance]",
                    "url": "https://www.who.int/guidance",
                },
                {
                    "citation_id": "abc-2",
                    "title": "Second source",
                    "url": "https://example.test/second",
                },
            ]
        }
    )
    events = [
        SimpleNamespace(
            type="tool/result",
            data={
                "turn_id": "turn-1",
                "name": "web_search",
                "status": "completed",
                "result": {"type": "tool_result", "output": search_output},
            },
        )
    ]

    sources = web_citation_sources_from_events(events, "turn-1")
    exported = export_web_citation_markdown(raw_content, events, "turn-1")

    assert set(sources) == {"abc-1", "abc-2"}
    assert raw_content == (
        "结论一。[cite:abc-1] 未知来源。[cite:missing] "
        "`示例 [cite:abc-1]`\\[cite:literal]"
    )
    assert "[WHO \\[guidance\\]](<https://www.who.int/guidance>)" in exported
    assert "[cite:missing]" not in exported
    assert "`示例 [cite:abc-1]`" in exported
    assert "\\[cite:literal]" in exported


def test_native_and_text_protocol_use_the_same_web_tool_schemas():
    tools = build_tools(
        runtime_context=PluginRuntimeContext(
            account_id=account_id_for("alice"),
            event_recorder=lambda _event: None,
        ),
    )
    schemas = tuple(
        ToolSchema(
            name=tool.name,
            description=tool.description,
            parameters=tool.input_schema,
        )
        for tool in tools
    )
    logical = ModelRequest.build(
        system="SYSTEM\n\nSKILL_CATALOG\nreport-query query reports",
        messages=[{"role": "user", "content": "latest guidance"}],
        tools=schemas,
    )
    native = ModelProviderService.prepare_transport_request(
        {"supports_tool_calling": True}, logical, "default"
    )
    text_request = ModelProviderService.prepare_transport_request(
        {"supports_tool_calling": False}, logical, "default"
    )

    assert native.tools == schemas
    assert text_request.tools == ()
    serialized = json.dumps([schema.as_dict() for schema in schemas], ensure_ascii=False)
    for schema in schemas:
        assert schema.name in text_request.system
    assert '"url"' not in serialized
    assert text_request.system.index("TEXT_TOOL_PROTOCOL") < text_request.system.index(
        "SKILL_CATALOG"
    )


def test_tavily_search_normalizes_results_and_discards_non_http_urls():
    def handler(request: httpx.Request):
        assert str(request.url) == "https://api.tavily.com/search"
        assert request.headers["authorization"] == "Bearer secret"
        payload = json.loads(request.content)
        assert payload["include_answer"] is False
        assert payload["include_raw_content"] is False
        assert payload["safe_search"] is True
        assert payload["chunks_per_source"] == 1
        return _json_response(
            {
                "request_id": "tavily-request",
                "usage": {"credits": 1},
                "results": [
                    {
                        "title": "WHO guidance",
                        "url": "https://www.who.int/guidance",
                        "content": "G" * 900,
                        "published_date": "2026-08-20",
                    },
                    {
                        "title": "unsafe",
                        "url": "file:///etc/passwd",
                        "content": "ignored",
                    },
                    {
                        "title": "credentials",
                        "url": "https://user:password@example.test/private",
                        "content": "ignored",
                    },
                ],
            }
        )

    result = TavilyAdapter(transport=httpx.MockTransport(handler)).search(
        "secret",
        {
            "query": "clinical guidance",
            "topic": "general",
            "time_range": "month",
            "result_limit": 5,
            "include_domains": ["who.int"],
            "exclude_domains": [],
        },
    )

    assert result == {
        "request_id": "tavily-request",
        "usage": {"unit": "credits", "amount": 1},
        "results": [
            {
                "title": "WHO guidance",
                "url": "https://www.who.int/guidance",
                "snippet": "G" * 900,
                "published_at": "2026-08-20",
            }
        ],
    }


def test_exa_search_uses_moderation_and_extracts_highlight_snippet():
    def handler(request: httpx.Request):
        assert str(request.url) == "https://api.exa.ai/search"
        assert request.headers["x-api-key"] == "exa-secret"
        payload = json.loads(request.content)
        assert payload["moderation"] is True
        assert "highlights" in payload["contents"]
        assert "summary" not in payload["contents"]
        assert payload["contents"]["highlights"] == {
            "query": "systematic review",
            "numSentences": 2,
            "highlightsPerUrl": 1,
        }
        return _json_response(
            {
                "requestId": "exa-request",
                "costDollars": {"total": 0.002},
                "results": [
                    {
                        "title": "Systematic review",
                        "url": "https://pubmed.ncbi.nlm.nih.gov/123/",
                        "highlights": ["A" * 500, "B" * 500],
                        "publishedDate": "2026-08-19T00:00:00Z",
                    }
                ],
            }
        )

    result = ExaAdapter(transport=httpx.MockTransport(handler)).search(
        "exa-secret", {"query": "systematic review", "result_limit": 3}
    )

    assert result["request_id"] == "exa-request"
    assert result["usage"] == {"unit": "usd", "amount": 0.002}
    assert result["results"][0]["snippet"] == "A" * 500 + "\n\n" + "B" * 500
    assert len(result["results"][0]["snippet"]) == 1002


def test_web_adapters_build_endpoints_from_the_configured_api_url():
    tavily = TavilyAdapter(api_url="https://gateway.example.test/tavily")
    exa = ExaAdapter(api_url="https://gateway.example.test/exa/")

    assert tavily.search_endpoint == "https://gateway.example.test/tavily/search"
    assert tavily.read_endpoint == "https://gateway.example.test/tavily/extract"
    assert exa.search_endpoint == "https://gateway.example.test/exa/search"
    assert exa.read_endpoint == "https://gateway.example.test/exa/contents"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "WEB_AUTHENTICATION_FAILED"),
        (429, "WEB_RATE_LIMITED"),
        (432, "WEB_QUOTA_EXCEEDED"),
        (503, "WEB_PROVIDER_UNAVAILABLE"),
    ],
)
def test_provider_http_errors_are_normalized(status, code):
    adapter = TavilyAdapter(
        transport=httpx.MockTransport(lambda _request: httpx.Response(status))
    )
    with pytest.raises(WebAccessError) as captured:
        adapter.search("secret", {"query": "test", "result_limit": 1})
    assert captured.value.code == code


def test_provider_timeout_malformed_json_and_large_body_are_normalized():
    def timeout_handler(request: httpx.Request):
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(WebAccessError) as timeout:
        TavilyAdapter(transport=httpx.MockTransport(timeout_handler)).search(
            "secret", {"query": "test"}
        )
    assert timeout.value.code == "WEB_TIMEOUT"

    with pytest.raises(WebAccessError) as malformed:
        TavilyAdapter(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(200, content=b"not-json")
            )
        ).search("secret", {"query": "test"})
    assert malformed.value.code == "WEB_INVALID_RESPONSE"

    with pytest.raises(WebAccessError) as too_large:
        TavilyAdapter(
            transport=httpx.MockTransport(
                lambda _request: httpx.Response(
                    200, content=b"x" * (8 * 1024 * 1024 + 1)
                )
            )
        ).search("secret", {"query": "test"})
    assert too_large.value.code == "WEB_RESPONSE_TOO_LARGE"


def test_tavily_read_preserves_partial_failures():
    adapter = TavilyAdapter(
        transport=httpx.MockTransport(
            lambda _request: _json_response(
                {
                    "request_id": "read-request",
                    "results": [
                        {
                            "url": "https://who.int/one",
                            "raw_content": "# Extracted\nContent",
                        }
                    ],
                    "failed_results": [
                        {"url": "https://who.int/two", "error": "blocked"}
                    ],
                }
            )
        )
    )
    result = adapter.read(
        "secret",
        urls=["https://who.int/one", "https://who.int/two"],
        query="guidance",
        mode="relevant",
    )

    assert result["pages"][0]["content"] == "# Extracted\nContent"
    assert result["failures"] == [
        {"url": "https://who.int/two", "message": "blocked"}
    ]


class FakeAdapter(WebProviderAdapter):
    provider_id = "tavily"

    def __init__(self):
        self.search_calls = []
        self.read_calls = []
        self.test_calls = []

    def search(self, api_key, request):
        self.search_calls.append((api_key, request))
        return {
            "request_id": "search-request",
            "usage": {"credits": 1},
            "results": [
                {
                    "title": "WHO",
                    "url": "https://www.who.int/health",
                    "snippet": "WHO summary",
                    "published_at": "2026-08-20",
                },
                {
                    "title": "Review",
                    "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                    "snippet": "Review summary",
                    "published_at": None,
                },
                {
                    "title": "Third",
                    "url": "https://example.org/third",
                    "snippet": "Third summary",
                    "published_at": None,
                },
            ]
            + [
                {
                    "title": f"Source {index}",
                    "url": f"https://example.org/source-{index}",
                    "snippet": f"Source {index} summary",
                    "published_at": None,
                }
                for index in range(4, 11)
            ],
        }

    def read(self, api_key, *, urls, query, mode):
        self.read_calls.append((api_key, urls, query, mode))
        if urls == ["https://example.org/third"]:
            return {
                "request_id": "read-request",
                "usage": {"credits": 1},
                "pages": [],
                "failures": [{"url": urls[0], "message": "blocked"}],
            }
        content = "A" * 25_000 if "who.int" in urls[0] else "B" * 25_000
        return {
            "request_id": "read-request",
            "usage": {"credits": 1},
            "pages": [{"url": urls[0], "content": content}],
            "failures": [],
        }

    def test(self, api_key):
        self.test_calls.append(api_key)


def _enabled_service(account, adapter, resolver=None):
    repository = WebAccessRepository()
    repository.save_credential(account, "tavily", "top-secret")
    repository.update(account, is_enabled=True)
    return WebAccessService(
        repository=repository,
        adapter_factory=lambda provider_id, api_url: adapter,
        observation_resolver=resolver,
    )


def test_search_validation_disabled_state_and_no_provider_fallback(isolated_data_root):
    adapter = FakeAdapter()
    service = WebAccessService(adapter_factory=lambda _provider_id, _api_url: adapter)

    with pytest.raises(WebAccessError) as disabled:
        service.search(account_id_for("alice"), query="latest guidance")
    assert disabled.value.code == "WEB_ACCESS_DISABLED"
    assert not adapter.search_calls

    repository = WebAccessRepository()
    repository.save_credential(account_id_for("alice"), "tavily", "secret")
    repository.update(account_id_for("alice"), is_enabled=True)
    service = WebAccessService(
        repository=repository,
        adapter_factory=lambda provider_id, _api_url: (_ for _ in ()).throw(
            WebAccessError("WEB_PROVIDER_UNAVAILABLE", provider_id)
        ),
    )
    with pytest.raises(WebAccessError) as unavailable:
        service.search(account_id_for("alice"), query="latest guidance")
    assert unavailable.value.code == "WEB_PROVIDER_UNAVAILABLE"


def test_search_uses_the_account_provider_api_url(isolated_data_root):
    adapter = FakeAdapter()
    observed_factory_arguments = []
    repository = WebAccessRepository()
    repository.update_provider_api_url(
        account_id_for("alice"),
        "tavily",
        "https://gateway.example.test/tavily",
    )
    repository.save_credential(account_id_for("alice"), "tavily", "secret")
    repository.update(account_id_for("alice"), is_enabled=True)
    service = WebAccessService(
        repository=repository,
        adapter_factory=lambda provider_id, api_url: (
            observed_factory_arguments.append((provider_id, api_url)) or adapter
        ),
    )

    service.search(account_id_for("alice"), query="latest guidance")

    assert observed_factory_arguments == [
        ("tavily", "https://gateway.example.test/tavily")
    ]


def test_search_and_read_outputs_are_losslessly_paginated(isolated_data_root):
    adapter = FakeAdapter()
    visible_search = {
        "provider": "tavily",
        "query": "current clinical guidance",
        "results": [
            {
                "result_index": 1,
                "citation_id": "searchabcd-1",
                "title": "WHO",
                "url": "https://www.who.int/health",
                "domain": "www.who.int",
                "snippet": "WHO summary",
                "published_at": "2026-08-20",
            },
            {
                "result_index": 2,
                "citation_id": "searchabcd-2",
                "title": "Review",
                "url": "https://pubmed.ncbi.nlm.nih.gov/1/",
                "domain": "pubmed.ncbi.nlm.nih.gov",
                "snippet": "Review summary",
                "published_at": None,
            },
            {
                "result_index": 3,
                "citation_id": "searchabcd-3",
                "title": "Third",
                "url": "https://example.org/third",
                "domain": "example.org",
                "snippet": "Third summary",
                "published_at": None,
            },
        ],
    }

    def resolver(**arguments):
        assert arguments["allowed_tools"] == {"web_search"}
        assert arguments["session_id"] == "session-1"
        assert arguments["visible_message_ids"] == {"message-1"}
        if arguments["call_id"] != "call-search":
            return None
        return {"output": visible_search}

    service = _enabled_service(account_id_for("alice"), adapter, resolver)
    searched = service.search(
        account_id_for("alice"),
        query="current clinical guidance",
        include_domains=["who.int"],
    )
    assert [item["result_index"] for item in searched["results"]] == list(
        range(1, 11)
    )
    assert re.fullmatch(r"[0-9a-f]{8}-1", searched["results"][0]["citation_id"])
    assert searched["provider"] == "tavily"
    assert searched["provider_request_id"] == "search-request"
    assert searched["total"] == 10
    assert adapter.search_calls[-1][1]["result_limit"] == 10
    assert len(adapter.search_calls) == 1
    assert "next_cursor" not in searched

    with pytest.raises(WebAccessError) as forged:
        service.read(
            account_id_for("alice"),
            search_call_id="forged",
            result_index=1,
            session_id="session-1",
            visible_message_ids=["message-1"],
        )
    assert forged.value.code == "WEB_SEARCH_REFERENCE_FORBIDDEN"

    with pytest.raises(WebAccessError) as out_of_range:
        service.read(
            account_id_for("alice"),
            search_call_id="call-search",
            result_index=4,
            session_id="session-1",
            visible_message_ids=["message-1"],
        )
    assert out_of_range.value.code == "WEB_RESULT_INDEX_NOT_FOUND"

    read_result = service.read(
        account_id_for("alice"),
        search_call_id="call-search",
        result_index=1,
        mode="full",
        session_id="session-1",
        visible_message_ids=["message-1"],
    )
    assert read_result["total_characters"] == 25_000
    assert read_result["pages"] == [
        {
            "result_index": 1,
            "citation_id": "searchabcd-1",
            "title": "WHO",
            "url": "https://www.who.int/health",
            "domain": "www.who.int",
            "published_at": "2026-08-20",
            "content_start": 0,
            "content_end": 10_000,
            "content": "A" * 10_000,
        },
        {
            "result_index": 1,
            "citation_id": "searchabcd-1",
            "title": "WHO",
            "url": "https://www.who.int/health",
            "domain": "www.who.int",
            "published_at": "2026-08-20",
            "content_start": 10_000,
            "content_end": 20_000,
            "content": "A" * 10_000,
        },
        {
            "result_index": 1,
            "citation_id": "searchabcd-1",
            "title": "WHO",
            "url": "https://www.who.int/health",
            "domain": "www.who.int",
            "published_at": "2026-08-20",
            "content_start": 20_000,
            "content_end": 25_000,
            "content": "A" * 5_000,
        },
    ]
    assert all("truncated" not in page for page in read_result["pages"])
    assert "".join(page["content"] for page in read_result["pages"]) == "A" * 25_000
    assert "next_cursor" not in read_result
    assert len(adapter.read_calls) == 1

    with pytest.raises(WebAccessError) as no_content:
        service.read(
            account_id_for("alice"),
            search_call_id="call-search",
            result_index=3,
            session_id="session-1",
            visible_message_ids=["message-1"],
        )
    assert no_content.value.code == "WEB_NO_CONTENT"
    assert no_content.value.details == {
        "failures": [
            {
                "result_index": 3,
                "url": "https://example.org/third",
                "message": "blocked",
            }
        ]
    }

def test_web_credentials_are_account_isolated_encrypted_and_only_explicitly_revealed(
    isolated_data_root,
):
    repository = WebAccessRepository()
    service = WebAccessService(repository=repository)
    service.save_credential(account_id_for("alice"), "tavily", "alice-plain-secret")

    assert repository.credential(account_id_for("alice"), "tavily") == "alice-plain-secret"
    assert repository.credential(account_id_for("bob"), "tavily") == ""
    settings = service.settings(account_id_for("alice"))
    assert settings["providers"][0]["has_api_key"] is True
    assert all("api_key" not in provider for provider in settings["providers"])
    assert service.reveal_credential(account_id_for("alice"), "tavily") == {
        "provider_id": "tavily",
        "api_key": "alice-plain-secret",
    }
    with pytest.raises(WebAccessError) as missing:
        service.reveal_credential(account_id_for("bob"), "tavily")
    assert missing.value.code == "WEB_NOT_CONFIGURED"

    config_database = app_paths().config_db(account_id_for("alice"))
    database_bytes = config_database.read_bytes()
    assert b"alice-plain-secret" not in database_bytes
    with sqlite3.connect(config_database) as connection:
        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
    assert tables == {
        "account_preferences",
        "model_providers",
        "models",
        "model_access_settings",
        "member_preferences",
        "conversation_preferences",
        "web_access_settings",
        "web_providers",
    }
    with sqlite3.connect(config_database) as connection:
        provider = connection.execute(
            "SELECT encrypted_api_key, is_configured "
            "FROM web_providers WHERE provider_id = 'tavily'"
        ).fetchone()
        columns = {row[1] for row in connection.execute("PRAGMA table_info(web_providers)")}
    assert "api_key" not in columns
    assert provider[0] is not None
    assert provider[1] == 1
    assert not (isolated_data_root / "alice" / "web_access").exists()
    assert app_paths().web_access_master_key.exists()
    assert app_paths().web_access_master_key != app_paths().provider_master_key


def test_web_access_api_lists_only_presence_and_reveals_on_explicit_request(isolated_data_root):
    from backend.app.main import create_app

    client = TestClient(create_app())
    signup = client.post(
        "/api/auth/sign_up",
        json={
            "account": "web_patient",
            "account_name": "联网测试",
            "password": "secret",
            "confirm_password": "secret",
        },
    )
    assert signup.status_code == 200

    initial = client.get("/api/account-settings/web-access")
    assert initial.status_code == 200
    assert initial.json()["is_enabled"] is False
    assert initial.json()["providers"] == [
        {
            "provider_id": "tavily",
            "provider_name": "Tavily",
            "api_url": "https://api.tavily.com",
            "has_api_key": False,
        },
        {
            "provider_id": "exa",
            "provider_name": "Exa",
            "api_url": "https://api.exa.ai",
            "has_api_key": False,
        },
    ]
    assert all("official_url" not in provider for provider in initial.json()["providers"])

    updated_url = client.patch(
        "/api/account-settings/web-access/providers/tavily",
        json={"api_url": "https://gateway.example.test/tavily/"},
    )
    assert updated_url.status_code == 200
    assert updated_url.json()["providers"][0]["api_url"] == (
        "https://gateway.example.test/tavily"
    )
    assert client.get("/api/account-settings/web-access").json()["providers"][0][
        "api_url"
    ] == "https://gateway.example.test/tavily"

    invalid_url = client.patch(
        "/api/account-settings/web-access/providers/tavily",
        json={"api_url": "file:///tmp/provider"},
    )
    assert invalid_url.status_code == 400

    enabled_without_key = client.patch(
        "/api/account-settings/web-access", json={"is_enabled": True}
    )
    assert enabled_without_key.status_code == 400

    saved = client.put(
        "/api/account-settings/web-access/providers/tavily/credential",
        json={"api_key": "api-secret-that-must-not-return"},
    )
    assert saved.status_code == 200
    assert "api-secret-that-must-not-return" not in saved.text
    assert saved.json()["providers"][0]["has_api_key"] is True

    revealed = client.post(
        "/api/account-settings/web-access/providers/tavily/credential/reveal"
    )
    assert revealed.status_code == 200
    assert revealed.json() == {
        "provider_id": "tavily",
        "api_key": "api-secret-that-must-not-return",
    }
    assert "no-store" in revealed.headers["cache-control"]
    assert revealed.headers["pragma"] == "no-cache"

    is_enabled = client.patch(
        "/api/account-settings/web-access", json={"is_enabled": True}
    )
    assert is_enabled.status_code == 200
    assert is_enabled.json()["is_enabled"] is True
    assert all("api_key" not in provider for provider in is_enabled.json()["providers"])
