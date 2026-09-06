from __future__ import annotations

import re
import secrets
from datetime import date
from typing import Any, Callable
from urllib.parse import urlsplit

from backend.app.core.time import local_now_iso
from backend.app.plugins.web.adapters import WebProviderAdapter, build_adapter
from backend.app.plugins.web.errors import WebAccessError
from backend.app.repositories.web_access_repository import (
    WEB_PROVIDER_IDS,
    WebAccessRepository,
)


AdapterFactory = Callable[[str, str], WebProviderAdapter]
ObservationResolver = Callable[..., dict[str, Any] | None]

_HOST_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_SEARCH_RESULT_WINDOW = 10
_READ_PAGE_SIZE = 10_000
_PROVIDER_METADATA = {
    "tavily": {
        "provider_id": "tavily",
        "provider_name": "Tavily",
        "api_url": "https://api.tavily.com",
    },
    "exa": {
        "provider_id": "exa",
        "provider_name": "Exa",
        "api_url": "https://api.exa.ai",
    },
}


def _default_adapter_factory(provider_id: str, api_url: str) -> WebProviderAdapter:
    return build_adapter(provider_id, api_url=api_url)


class WebAccessService:
    def __init__(
        self,
        *,
        repository: WebAccessRepository | None = None,
        adapter_factory: AdapterFactory | None = None,
        observation_resolver: ObservationResolver | None = None,
    ):
        self.repository = repository or WebAccessRepository()
        self._adapter_factory = adapter_factory or _default_adapter_factory
        self._observation_resolver = observation_resolver

    def for_runtime(
        self, observation_resolver: ObservationResolver | None
    ) -> "WebAccessService":
        return WebAccessService(
            repository=self.repository,
            adapter_factory=self._adapter_factory,
            observation_resolver=observation_resolver,
        )

    @staticmethod
    def _provider_id(provider_id: str) -> str:
        normalized = str(provider_id or "").strip().lower()
        if normalized not in WEB_PROVIDER_IDS:
            raise ValueError("不支持的联网服务。")
        return normalized

    @staticmethod
    def _api_url(value: str) -> str:
        normalized = str(value or "").strip().rstrip("/")
        if not normalized or len(normalized) > 2048:
            raise ValueError("API 地址不能为空且长度不能超过 2048 个字符。")
        try:
            parsed = urlsplit(normalized)
            port = parsed.port
        except ValueError as exc:
            raise ValueError("API 地址无效。") from exc
        if (
            parsed.scheme.lower() not in {"http", "https"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or port is not None and not 0 < port < 65536
        ):
            raise ValueError("API 地址必须是有效的 HTTP 或 HTTPS 地址，且不能包含查询参数或片段。")
        return normalized

    def _adapter(self, provider_id: str, api_url: str) -> WebProviderAdapter:
        return self._adapter_factory(provider_id, api_url)

    def settings(self, account_id: str) -> dict[str, Any]:
        stored = self.repository.get(account_id)
        configured_providers = set(stored["configured_providers"])
        provider_api_urls = stored["provider_api_urls"]
        return {
            "is_enabled": bool(stored["is_enabled"]),
            "active_provider_id": stored["active_provider_id"],
            "providers": [
                {
                    **_PROVIDER_METADATA[provider_id],
                    "api_url": provider_api_urls.get(
                        provider_id,
                        _PROVIDER_METADATA[provider_id]["api_url"],
                    ),
                    "has_api_key": provider_id in configured_providers,
                }
                for provider_id in WEB_PROVIDER_IDS
            ],
        }

    def update_settings(
        self,
        account_id: str,
        *,
        is_enabled: bool | None = None,
        active_provider_id: str | None = None,
    ) -> dict[str, Any]:
        if is_enabled is None and active_provider_id is None:
            raise ValueError("至少需要更新 is_enabled 或 active_provider_id。")
        self.repository.update(
            account_id,
            is_enabled=is_enabled,
            active_provider_id=active_provider_id,
        )
        return self.settings(account_id)

    def update_provider_api_url(
        self,
        account_id: str,
        provider_id: str,
        api_url: str,
    ) -> dict[str, Any]:
        provider = self._provider_id(provider_id)
        self.repository.update_provider_api_url(
            account_id,
            provider,
            self._api_url(api_url),
        )
        return self.settings(account_id)

    def save_credential(
        self, account_id: str, provider_id: str, api_key: str
    ) -> dict[str, Any]:
        self.repository.save_credential(account_id, self._provider_id(provider_id), api_key)
        return self.settings(account_id)

    def reveal_credential(self, account_id: str, provider_id: str) -> dict[str, Any]:
        provider = self._provider_id(provider_id)
        api_key = self.repository.credential(account_id, provider)
        if not api_key:
            raise WebAccessError(
                "WEB_NOT_CONFIGURED", "该联网服务尚未配置 API key。"
            )
        return {"provider_id": provider, "api_key": api_key}

    def delete_credential(self, account_id: str, provider_id: str) -> dict[str, Any]:
        self.repository.delete_credential(account_id, self._provider_id(provider_id))
        return self.settings(account_id)

    def test_provider(
        self,
        account_id: str,
        provider_id: str,
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        provider = self._provider_id(provider_id)
        secret = str(api_key or "").strip() or self.repository.credential(
            account_id, provider
        )
        if not secret:
            raise WebAccessError("WEB_NOT_CONFIGURED", "该联网服务尚未配置 API key。")
        stored = self.repository.get(account_id)
        api_url = stored["provider_api_urls"].get(
            provider,
            _PROVIDER_METADATA[provider]["api_url"],
        )
        self._adapter(provider, api_url).test(secret)
        return {
            "provider_id": provider,
            "reachable": True,
            "message": f'{_PROVIDER_METADATA[provider]["provider_name"]} 连接成功。',
        }

    @staticmethod
    def _date(value: Any, *, field: str) -> str | None:
        if value is None or value == "":
            return None
        normalized = str(value).strip()
        try:
            date.fromisoformat(normalized)
        except ValueError as exc:
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", f"{field} 必须是 YYYY-MM-DD 日期。"
            ) from exc
        return normalized

    @staticmethod
    def _domains(value: Any, *, field: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or len(value) > 10:
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", f"{field} 最多接受 10 个主机名。"
            )
        normalized: list[str] = []
        for item in value:
            hostname = str(item or "").strip().lower().rstrip(".")
            if (
                not hostname
                or len(hostname) > 253
                or "://" in hostname
                or any(character in hostname for character in "/?#@:")
                or any(not _HOST_LABEL.fullmatch(label) for label in hostname.split("."))
            ):
                raise WebAccessError(
                    "WEB_ARGUMENTS_INVALID", f"{field} 只接受不含协议、路径或端口的主机名。"
                )
            if hostname not in normalized:
                normalized.append(hostname)
        return normalized

    @classmethod
    def _search_request(cls, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query or len(query) > 500:
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", "query 必须包含 1 至 500 个字符。"
            )
        topic = str(arguments.get("topic") or "general")
        if topic not in {"general", "news"}:
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", "topic 必须是 general 或 news。"
            )
        time_range = arguments.get("time_range")
        if time_range is not None and time_range not in {"day", "week", "month", "year"}:
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", "time_range 取值无效。"
            )
        start_date = cls._date(arguments.get("start_date"), field="start_date")
        end_date = cls._date(arguments.get("end_date"), field="end_date")
        if time_range and (start_date or end_date):
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", "time_range 与精确日期范围不能同时使用。"
            )
        if start_date and end_date and start_date > end_date:
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", "start_date 不能晚于 end_date。"
            )
        include_domains = cls._domains(
            arguments.get("include_domains"), field="include_domains"
        )
        exclude_domains = cls._domains(
            arguments.get("exclude_domains"), field="exclude_domains"
        )
        if set(include_domains) & set(exclude_domains):
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", "同一主机名不能同时包含和排除。"
            )
        return {
            "query": query,
            "topic": topic,
            "time_range": time_range,
            "start_date": start_date,
            "end_date": end_date,
            "result_limit": _SEARCH_RESULT_WINDOW,
            "include_domains": include_domains,
            "exclude_domains": exclude_domains,
        }

    def _enabled_provider(self, account_id: str) -> tuple[str, str, str]:
        settings = self.repository.get(account_id)
        if not settings["is_enabled"]:
            raise WebAccessError("WEB_ACCESS_DISABLED", "当前账号未启用联网。")
        provider = str(settings["active_provider_id"])
        api_key = self.repository.credential(account_id, provider)
        if not api_key:
            raise WebAccessError(
                "WEB_NOT_CONFIGURED", "当前联网服务尚未配置 API key。"
            )
        api_url = settings["provider_api_urls"].get(
            provider,
            _PROVIDER_METADATA[provider]["api_url"],
        )
        return provider, api_key, api_url

    def search(self, account_id: str, **arguments: Any) -> dict[str, Any]:
        request = self._search_request(arguments)
        provider, api_key, api_url = self._enabled_provider(account_id)
        normalized = self._adapter(provider, api_url).search(api_key, request)
        results = []
        seen: set[str] = set()
        citation_prefix = secrets.token_hex(4)
        for raw in normalized.get("results") or []:
            if not isinstance(raw, dict):
                continue
            url = str(raw.get("url") or "")
            try:
                domain = str(urlsplit(url).hostname or "").lower()
            except ValueError:
                continue
            if not domain or url in seen:
                continue
            seen.add(url)
            results.append(
                {
                    "result_index": len(results) + 1,
                    "citation_id": f"{citation_prefix}-{len(results) + 1}",
                    "title": str(raw.get("title") or url),
                    "url": url,
                    "domain": domain,
                    "snippet": str(raw.get("snippet") or ""),
                    "published_at": raw.get("published_at"),
                }
            )
            if len(results) >= request["result_limit"]:
                break
        return {
            "provider": provider,
            "query": request["query"],
            "searched_at": local_now_iso(),
            "provider_request_id": str(normalized.get("request_id") or ""),
            "usage": normalized.get("usage") if isinstance(normalized.get("usage"), dict) else {},
            "total": len(results),
            "results": results,
        }

    def read(
        self,
        account_id: str,
        *,
        search_call_id: str,
        result_index: int,
        mode: str = "relevant",
        session_id: str,
        visible_message_ids: list[str],
        **_runtime_arguments: Any,
    ) -> dict[str, Any]:
        call_id = str(search_call_id or "").strip()
        if not call_id:
            raise WebAccessError(
                "WEB_SEARCH_REFERENCE_INVALID", "search_call_id 不能为空。"
            )
        if mode not in {"relevant", "full"}:
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", "mode 必须是 relevant 或 full。"
            )
        if (
            isinstance(result_index, bool)
            or not isinstance(result_index, int)
            or result_index < 1
        ):
            raise WebAccessError(
                "WEB_ARGUMENTS_INVALID", "result_index 必须是正整数。"
            )
        if self._observation_resolver is None:
            raise WebAccessError(
                "WEB_SEARCH_REFERENCE_UNAVAILABLE", "当前运行环境无法解析搜索观测。"
            )
        resolved = self._observation_resolver(
            call_id=call_id,
            allowed_tools={"web_search"},
            session_id=str(session_id),
            visible_message_ids={str(item) for item in visible_message_ids},
        )
        if not isinstance(resolved, dict):
            raise WebAccessError(
                "WEB_SEARCH_REFERENCE_FORBIDDEN",
                "搜索结果不属于当前可见会话分支或已经不可用。",
            )
        output = resolved.get("output")
        results = output.get("results") if isinstance(output, dict) else None
        if not isinstance(results, list):
            raise WebAccessError(
                "WEB_SEARCH_REFERENCE_INVALID", "搜索观测不包含有效结果。"
            )
        indexed = {
            item.get("result_index"): item
            for item in results
            if isinstance(item, dict)
            and isinstance(item.get("result_index"), int)
            and isinstance(item.get("citation_id"), str)
            and item.get("citation_id")
        }
        selected = indexed.get(result_index)
        if not isinstance(selected, dict):
            raise WebAccessError(
                "WEB_RESULT_INDEX_NOT_FOUND", f"搜索结果索引 {result_index} 不存在。"
            )

        provider, api_key, api_url = self._enabled_provider(account_id)
        if str(output.get("provider") or "") != provider:
            raise WebAccessError(
                "WEB_PROVIDER_CHANGED",
                "当前联网服务已改变，不能用另一服务读取既有搜索结果。",
            )
        url = str(selected.get("url") or "")
        extracted = self._adapter(provider, api_url).read(
            api_key,
            urls=[url],
            query=str(output.get("query") or ""),
            mode=mode,
        )
        extracted_page = next(
            (
                item
                for item in extracted.get("pages") or []
                if isinstance(item, dict) and str(item.get("url") or "") == url
            ),
            None,
        )
        content = str(extracted_page.get("content") or "") if extracted_page else ""
        if not content:
            failure_message = next(
                (
                    str(item.get("message") or "无法提取正文。")
                    for item in extracted.get("failures") or []
                    if isinstance(item, dict) and str(item.get("url") or "") == url
                ),
                "联网服务未返回可用正文。",
            )
            raise WebAccessError(
                "WEB_NO_CONTENT",
                "选中的搜索结果未取得正文。",
                details={
                    "failures": [
                        {
                            "result_index": selected["result_index"],
                            "url": url,
                            "message": failure_message,
                        }
                    ]
                },
            )
        total_characters = len(content)
        pages = []
        for content_start in range(0, total_characters, _READ_PAGE_SIZE):
            content_end = min(content_start + _READ_PAGE_SIZE, total_characters)
            pages.append(
                {
                    "result_index": selected["result_index"],
                    "citation_id": selected["citation_id"],
                    "title": selected.get("title"),
                    "url": url,
                    "domain": selected.get("domain"),
                    "published_at": selected.get("published_at"),
                    "content_start": content_start,
                    "content_end": content_end,
                    "content": content[content_start:content_end],
                }
            )
        return {
            "provider": provider,
            "search_call_id": call_id,
            "query": str(output.get("query") or ""),
            "mode": mode,
            "read_at": local_now_iso(),
            "provider_request_id": str(extracted.get("request_id") or ""),
            "usage": extracted.get("usage") if isinstance(extracted.get("usage"), dict) else {},
            "total_characters": total_characters,
            "pages": pages,
        }
