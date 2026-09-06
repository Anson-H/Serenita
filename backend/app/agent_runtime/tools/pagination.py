from typing import Any
from backend.app.agent_runtime.tools.base import ToolResult


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
