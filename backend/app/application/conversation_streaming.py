import json
from typing import Any


def sse_event(name: str, payload: dict[str, Any]) -> str:
    """Serialize one named Server-Sent Event using the conversation wire format."""
    return f"event: {name}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
