from __future__ import annotations
from backend.app.agent_runtime.tools.pagination import paginated_collection

from typing import Any

from backend.app.agent_runtime.tools.base import Tool, ToolResult
from backend.app.plugins.web.service import WebAccessService




class WebSearchTool(Tool):
    name = "web_search"
    model_exposure = "direct"
    description = "搜索公开互联网，返回搜索结果摘要和引用标识。"
    input_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "query": {"type": "string", "description": "发送给当前联网服务的搜索查询，长度为 1 至 500 个字符。"},
            "topic": {
                "type": "string",
                "enum": ["general", "news"],
                "description": "搜索主题；general 表示普通网页，news 表示新闻，省略时默认为 general。",
            },
            "time_range": {
                "type": "string",
                "enum": ["day", "week", "month", "year"],
                "description": "相对当前日期的发布时间范围；与 start_date、end_date 互斥，省略时不使用相对时间筛选。",
            },
            "start_date": {
                "type": "string",
                "description": "精确发布时间范围的可选起始日期，格式 YYYY-MM-DD；与 time_range 互斥，省略或传空字符串时不设起始日期。",
            },
            "end_date": {
                "type": "string",
                "description": "精确发布时间范围的可选结束日期，格式 YYYY-MM-DD；与 time_range 互斥，省略或传空字符串时不设结束日期。",
            },
            "include_domains": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
                "description": "优先包含的主机名列表，最多 10 项且不含协议、端口或路径；不能与 exclude_domains 重复，省略或传空数组时不限定。",
            },
            "exclude_domains": {
                "type": "array",
                "items": {"type": "string"},
                "maxItems": 10,
                "description": "排除的主机名列表，最多 10 项且不含协议、端口或路径；不能与 include_domains 重复，省略或传空数组时不排除。",
            },
        },
        "required": ["query"],
    }

    def __init__(self, *, service: WebAccessService):
        self._service = service

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        account_id = str(arguments.pop("account_id"))
        return paginated_collection(
            name=self.name,
            output=self._service.search(account_id, **arguments),
            collection_field="results",
        )


class WebReadTool(Tool):
    name = "web_read"
    model_exposure = "direct"
    bind_conversation = True
    description = "读取一条既有搜索结果的网页正文，并保留其引用标识。"
    input_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "search_call_id": {
                "type": "string",
                "description": "对应 `web_search` 工具调用的 `tool_call_id`，在工具观测外层记录为 `call_id`；必须是工具调用标识，不接受 URL 或搜索结果的 `citation_id`。",
            },
            "result_index": {
                "type": "integer",
                "minimum": 1,
                "description": "要读取的搜索结果在对应 `web_search` 结果列表中的一基索引。",
            },
            "mode": {
                "type": "string",
                "enum": ["relevant", "full"],
                "description": "正文读取模式；relevant 返回相关正文，full 返回清洗后的完整 Markdown，省略时默认为 relevant。",
            },
        },
        "required": ["search_call_id", "result_index"],
    }

    def __init__(self, *, service: WebAccessService):
        self._service = service

    def run(self, arguments: dict[str, Any]) -> ToolResult:
        account_id = str(arguments.pop("account_id"))
        return paginated_collection(
            name=self.name,
            output=self._service.read(account_id, **arguments),
            collection_field="pages",
        )
