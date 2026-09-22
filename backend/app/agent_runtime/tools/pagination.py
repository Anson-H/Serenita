from dataclasses import replace
import json
from typing import Any, Callable
from backend.app.agent_runtime.tools.base import ToolResult


def automatic_pages(
    load: Callable[[Any], ToolResult], *, next_field: str = "next_cursor",
    max_pages: int = 1000,
) -> ToolResult:
    """Keep storage pagination private; let the Harness consume one page at a time."""
    seen: set[str] = set()

    def read(position, number):
        if number > max_pages:
            raise ValueError("查询超过自动读取页数上限，已读部分不代表完整查询。")
        key = json.dumps(position, sort_keys=True)
        if key in seen:
            raise ValueError("查询返回重复的分页位置，已停止读取，查询尚未完成。")
        seen.add(key)
        result = load(position)
        output = dict(result.output)
        following = output.pop(next_field, None)
        output.pop("has_more", None)
        output["pagination"] = {"page": number, "complete": following is None}
        return replace(
            result, output=output,
            next_page=(lambda: read(following, number + 1)) if following is not None else None,
        )

    return read(None, 1)


def paginated_collection(
    *,
    name: str,
    output: dict[str, Any],
    collection_field: str,
    page_size: int = 1,
    effects: dict[str, Any] | None = None,
) -> ToolResult:
    if page_size < 1:
        raise ValueError("page_size must be positive")
    items = output.get(collection_field)
    if not isinstance(items, list):
        items = []
    return ToolResult(
        name=name,
        output={
            key: ([] if key == collection_field else value)
            for key, value in output.items()
        },
        effects=effects or {},
        logical_pages=tuple(
            {collection_field: items[index : index + page_size]}
            for index in range(0, len(items), page_size)
        ),
    )
