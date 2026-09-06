from typing import Any
from urllib.parse import quote


def report_response(detail: dict[str, Any], member_id: str) -> dict[str, Any]:
    sources = []
    for source in detail.get("sources", []):
        url = f"/api/members/{quote(member_id, safe='')}/reports/{quote(detail['report_id'], safe='')}/source-files/{quote(source['resource_id'], safe='')}"
        projected = {**source, "download_url": url}
        if source.get("mime_type") in {"image/jpeg", "image/png", "image/heic", "application/pdf"}:
            projected["thumbnail_url"] = f"{url}/thumbnail"
        sources.append(projected)
    return {**detail, "sources": sources}
