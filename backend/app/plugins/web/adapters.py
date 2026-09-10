from __future__ import annotations

import json
import time
from copy import copy
from contextlib import ExitStack
from threading import Event, Timer
from datetime import timedelta
from typing import Any
from urllib.parse import urlsplit

import httpx

from backend.app.core.time import local_now
from backend.app.plugins.web.errors import WebAccessError
from backend.app.core.cancellation import CancellationToken


MAX_RESPONSE_BYTES = 8 * 1024 * 1024
SEARCH_TIMEOUT_SECONDS = 20.0
READ_TIMEOUT_SECONDS = 45.0


def public_http_url(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = urlsplit(text)
        port = parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None and not 0 < port < 65536
    ):
        return None
    return text


def _text(value: Any, *, limit: int | None = None) -> str:
    text = str(value or "").strip()
    return text[:limit] if limit is not None else text


def _usage(unit: str, amount: Any) -> dict[str, Any]:
    if isinstance(amount, bool) or not isinstance(amount, (int, float)):
        return {}
    return {"unit": unit, "amount": amount}


class WebProviderAdapter:
    provider_id = ""
    default_api_url = ""
    search_path = ""
    read_path = ""
    search_endpoint = ""
    read_endpoint = ""

    def __init__(
        self,
        *,
        api_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ):
        self._transport = transport
        api_url = str(api_url or self.default_api_url).rstrip("/")
        self.search_endpoint = f"{api_url}{self.search_path}"
        self.read_endpoint = f"{api_url}{self.read_path}"
        self.cancellation_token = None
        self.deadline = None

    def for_execution(self, cancellation_token: CancellationToken | None, deadline: float | None):
        adapter = copy(self)
        adapter.cancellation_token = cancellation_token
        adapter.deadline = deadline
        return adapter

    def _headers(self, api_key: str) -> dict[str, str]:
        raise NotImplementedError

    def _request_json(
        self,
        *,
        endpoint: str,
        api_key: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> tuple[dict[str, Any], dict[str, str]]:
        token = self.cancellation_token
        deadline = min(
            time.monotonic() + timeout,
            self.deadline if self.deadline is not None else float("inf"),
        )
        expired = Event()

        def check_active():
            if token is not None:
                token.raise_if_cancelled()
            if expired.is_set() or time.monotonic() >= deadline:
                raise WebAccessError("WEB_TIMEOUT", "联网服务请求超时。")

        check_active()
        try:
            with ExitStack() as stack:
                client = stack.enter_context(httpx.Client(
                    transport=self._transport,
                    follow_redirects=False,
                    trust_env=False,
                    timeout=max(0.001, deadline - time.monotonic()),
                ))
                response_holder = []

                def close_request():
                    for handle in [*response_holder, client]:
                        try:
                            handle.close()
                        except Exception:
                            pass

                if token is not None:
                    stack.callback(token.register(close_request))

                def expire():
                    expired.set()
                    close_request()

                timer = Timer(max(0.001, deadline - time.monotonic()), expire)
                timer.daemon = True
                timer.start()
                stack.callback(timer.cancel)
                check_active()
                response = stack.enter_context(client.stream(
                    "POST",
                    endpoint,
                    headers=self._headers(api_key),
                    json=payload,
                ))
                response_holder.append(response)
                check_active()
                body = bytearray()
                for chunk in response.iter_bytes():
                    check_active()
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise WebAccessError("WEB_RESPONSE_TOO_LARGE", "联网服务响应超过 8 MiB 安全上限。")
                check_active()
                status_code = response.status_code
                response_headers = dict(response.headers)
        except WebAccessError:
            raise
        except httpx.TimeoutException as exc:
            check_active()
            raise WebAccessError("WEB_TIMEOUT", "联网服务请求超时。") from exc
        except httpx.HTTPError as exc:
            check_active()
            raise WebAccessError(
                "WEB_PROVIDER_UNAVAILABLE", "无法连接当前联网服务。"
            ) from exc
        except Exception:
            check_active()
            raise

        if status_code in {401, 403}:
            raise WebAccessError("WEB_AUTHENTICATION_FAILED", "联网服务 API key 无效。")
        if status_code == 429:
            raise WebAccessError("WEB_RATE_LIMITED", "联网服务请求过于频繁。")
        if status_code in {402, 432, 433}:
            raise WebAccessError("WEB_QUOTA_EXCEEDED", "联网服务额度不足或已达上限。")
        if status_code >= 500:
            raise WebAccessError(
                "WEB_PROVIDER_UNAVAILABLE", "当前联网服务暂时不可用。"
            )
        if status_code < 200 or status_code >= 300:
            raise WebAccessError(
                "WEB_PROVIDER_REJECTED", "联网服务拒绝了本次请求。"
            )
        try:
            decoded = json.loads(bytes(body))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise WebAccessError(
                "WEB_INVALID_RESPONSE", "联网服务返回了无效 JSON。"
            ) from exc
        if not isinstance(decoded, dict):
            raise WebAccessError(
                "WEB_INVALID_RESPONSE", "联网服务响应结构无效。"
            )
        return decoded, response_headers

    def search(self, api_key: str, request: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def read(
        self,
        api_key: str,
        *,
        urls: list[str],
        query: str,
        mode: str,
    ) -> dict[str, Any]:
        raise NotImplementedError

    def test(self, api_key: str) -> None:
        self.search(api_key, {"query": "World Health Organization", "result_limit": 1})


class TavilyAdapter(WebProviderAdapter):
    provider_id = "tavily"
    default_api_url = "https://api.tavily.com"
    search_path = "/search"
    read_path = "/extract"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def search(self, api_key: str, request: dict[str, Any]) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "query": request["query"],
            "search_depth": "basic",
            "chunks_per_source": 1,
            "max_results": request.get("result_limit", 10),
            "topic": request.get("topic", "general"),
            "include_answer": False,
            "include_raw_content": False,
            "include_images": False,
            "include_favicon": False,
            "include_usage": True,
            "safe_search": True,
        }
        for name in (
            "time_range",
            "start_date",
            "end_date",
            "include_domains",
            "exclude_domains",
        ):
            value = request.get(name)
            if value:
                payload[name] = value
        response, headers = self._request_json(
            endpoint=self.search_endpoint,
            api_key=api_key,
            payload=payload,
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        raw_results = response.get("results")
        if not isinstance(raw_results, list):
            raise WebAccessError(
                "WEB_INVALID_RESPONSE", "Tavily 搜索响应缺少结果列表。"
            )
        results = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            url = public_http_url(raw.get("url"))
            if not url:
                continue
            results.append(
                {
                    "title": _text(raw.get("title"), limit=500) or url,
                    "url": url,
                    "snippet": _text(raw.get("content")),
                    "published_at": _text(
                        raw.get("published_date") or raw.get("publishedDate"),
                        limit=100,
                    )
                    or None,
                }
            )
        return {
            "request_id": _text(
                response.get("request_id") or headers.get("x-request-id"), limit=200
            ),
            "usage": _usage(
                "credits",
                response.get("usage", {}).get("credits")
                if isinstance(response.get("usage"), dict)
                else None,
            ),
            "results": results,
        }

    def read(
        self,
        api_key: str,
        *,
        urls: list[str],
        query: str,
        mode: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "urls": urls,
            "extract_depth": "basic" if mode == "relevant" else "advanced",
            "include_images": False,
            "include_favicon": False,
            "format": "markdown",
            "timeout": 40,
            "include_usage": True,
        }
        if mode == "relevant":
            payload.update({"query": query, "chunks_per_source": 5})
        response, headers = self._request_json(
            endpoint=self.read_endpoint,
            api_key=api_key,
            payload=payload,
            timeout=READ_TIMEOUT_SECONDS,
        )
        raw_results = response.get("results")
        failed_results = response.get("failed_results") or []
        if not isinstance(raw_results, list) or not isinstance(failed_results, list):
            raise WebAccessError(
                "WEB_INVALID_RESPONSE", "Tavily 正文响应结构无效。"
            )
        pages = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            url = public_http_url(raw.get("url"))
            if not url:
                continue
            content = _text(raw.get("raw_content"))
            if content:
                pages.append({"url": url, "content": content})
        failures = []
        for raw in failed_results:
            if not isinstance(raw, dict):
                continue
            url = public_http_url(raw.get("url"))
            if url:
                failures.append(
                    {"url": url, "message": _text(raw.get("error"), limit=500) or "无法提取正文。"}
                )
        return {
            "request_id": _text(
                response.get("request_id") or headers.get("x-request-id"), limit=200
            ),
            "usage": _usage(
                "credits",
                response.get("usage", {}).get("credits")
                if isinstance(response.get("usage"), dict)
                else None,
            ),
            "pages": pages,
            "failures": failures,
        }


class ExaAdapter(WebProviderAdapter):
    provider_id = "exa"
    default_api_url = "https://api.exa.ai"
    search_path = "/search"
    read_path = "/contents"

    def _headers(self, api_key: str) -> dict[str, str]:
        return {
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    @staticmethod
    def _relative_start_date(time_range: str) -> str:
        days = {"day": 1, "week": 7, "month": 31, "year": 366}[time_range]
        return (local_now() - timedelta(days=days)).isoformat()

    def search(self, api_key: str, request: dict[str, Any]) -> dict[str, Any]:
        query = str(request["query"])
        payload: dict[str, Any] = {
            "query": query,
            "type": "auto",
            "numResults": request.get("result_limit", 10),
            "moderation": True,
            "contents": {
                "highlights": {
                    "query": query,
                    "numSentences": 2,
                    "highlightsPerUrl": 1,
                }
            },
        }
        if request.get("topic") == "news":
            payload["category"] = "news"
        if request.get("time_range"):
            payload["startPublishedDate"] = self._relative_start_date(
                request["time_range"]
            )
        if request.get("start_date"):
            payload["startPublishedDate"] = f'{request["start_date"]}T00:00:00Z'
        if request.get("end_date"):
            payload["endPublishedDate"] = f'{request["end_date"]}T23:59:59Z'
        if request.get("include_domains"):
            payload["includeDomains"] = request["include_domains"]
        if request.get("exclude_domains"):
            payload["excludeDomains"] = request["exclude_domains"]
        response, headers = self._request_json(
            endpoint=self.search_endpoint,
            api_key=api_key,
            payload=payload,
            timeout=SEARCH_TIMEOUT_SECONDS,
        )
        raw_results = response.get("results")
        if not isinstance(raw_results, list):
            raise WebAccessError(
                "WEB_INVALID_RESPONSE", "Exa 搜索响应缺少结果列表。"
            )
        results = []
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            url = public_http_url(raw.get("url"))
            if not url:
                continue
            highlights = raw.get("highlights")
            snippet = "\n\n".join(
                _text(item) for item in highlights if _text(item)
            ) if isinstance(highlights, list) else ""
            results.append(
                {
                    "title": _text(raw.get("title"), limit=500) or url,
                    "url": url,
                    "snippet": _text(snippet or raw.get("text")),
                    "published_at": _text(raw.get("publishedDate"), limit=100) or None,
                }
            )
        return {
            "request_id": _text(
                response.get("requestId") or headers.get("x-request-id"), limit=200
            ),
            "usage": _usage(
                "usd",
                response.get("costDollars", {}).get("total")
                if isinstance(response.get("costDollars"), dict)
                else None,
            ),
            "results": results,
        }

    def read(
        self,
        api_key: str,
        *,
        urls: list[str],
        query: str,
        mode: str,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"ids": urls}
        if mode == "relevant":
            payload["highlights"] = {
                "query": query,
                "numSentences": 5,
                "highlightsPerUrl": 5,
            }
        else:
            payload["text"] = True
        response, headers = self._request_json(
            endpoint=self.read_endpoint,
            api_key=api_key,
            payload=payload,
            timeout=READ_TIMEOUT_SECONDS,
        )
        raw_results = response.get("results")
        if not isinstance(raw_results, list):
            raise WebAccessError(
                "WEB_INVALID_RESPONSE", "Exa 正文响应缺少结果列表。"
            )
        pages = []
        returned_urls: set[str] = set()
        for raw in raw_results:
            if not isinstance(raw, dict):
                continue
            url = public_http_url(raw.get("url") or raw.get("id"))
            if not url or url not in urls:
                continue
            if mode == "relevant":
                highlights = raw.get("highlights")
                content = "\n\n".join(
                    _text(item) for item in highlights if _text(item)
                ) if isinstance(highlights, list) else ""
            else:
                content = _text(raw.get("text"))
            if content:
                returned_urls.add(url)
                pages.append({"url": url, "content": content})
        failures = [
            {"url": url, "message": "Exa 未返回可用正文。"}
            for url in urls
            if url not in returned_urls
        ]
        return {
            "request_id": _text(
                response.get("requestId") or headers.get("x-request-id"), limit=200
            ),
            "usage": _usage(
                "usd",
                response.get("costDollars", {}).get("total")
                if isinstance(response.get("costDollars"), dict)
                else None,
            ),
            "pages": pages,
            "failures": failures,
        }


def build_adapter(
    provider_id: str,
    *,
    api_url: str | None = None,
    transport: httpx.BaseTransport | None = None,
) -> WebProviderAdapter:
    if provider_id == "tavily":
        return TavilyAdapter(api_url=api_url, transport=transport)
    if provider_id == "exa":
        return ExaAdapter(api_url=api_url, transport=transport)
    raise ValueError("不支持的联网服务。")
