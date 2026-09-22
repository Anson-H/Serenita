"""提供会话文本分片与 SSE 事件编码，供执行记录和订阅共同使用。"""

import json
from typing import Any, Iterator


STREAM_CHUNK_CHARS = 16


def stream_text_chunks(text: str) -> Iterator[str]:
    content = text or ""
    for index in range(0, len(content), STREAM_CHUNK_CHARS):
        yield content[index : index + STREAM_CHUNK_CHARS]


def sse_event(name: str, payload: dict[str, Any]) -> str:
    """Serialize one named Server-Sent Event using the conversation wire format."""
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
