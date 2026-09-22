from urllib.parse import quote

from fastapi import APIRouter, Depends, Request, UploadFile
from fastapi.responses import Response

from backend.app.api.dependencies import require_current_user
from backend.app.domain.knowledge import MAX_FILE_BYTES


router = APIRouter(prefix="/api/knowledge/documents", tags=["knowledge"])


def service(request: Request):
    return request.app.state.services.knowledge


@router.get("")
def catalog(cursor: str | None = None, limit: int = 30,
            user=Depends(require_current_user), knowledge=Depends(service)):
    return knowledge.catalog(user.account_id, cursor=cursor, limit=limit)


@router.post("", status_code=201)
def upload(file: UploadFile, user=Depends(require_current_user), knowledge=Depends(service)):
    return knowledge.upload(user.account_id, file.filename, file.file.read(MAX_FILE_BYTES + 1))


@router.get("/search")
def search(query: str, limit: int = 8, user=Depends(require_current_user), knowledge=Depends(service)):
    return knowledge.search(user.account_id, query, limit=limit)


@router.get("/{document_id}")
def read(document_id: str, segment_start: int = 1, segment_count: int = 4,
         user=Depends(require_current_user), knowledge=Depends(service)):
    return knowledge.read(user.account_id, document_id, segment_start=segment_start, segment_count=segment_count)


@router.get("/{document_id}/content")
def content(document_id: str, user=Depends(require_current_user), knowledge=Depends(service)):
    document = knowledge.original(user.account_id, document_id)
    mime_type = document["mime_type"]
    disposition = "inline" if mime_type in {"application/pdf", "text/plain", "text/markdown"} else "attachment"
    return Response(document["content_bytes"], media_type="text/plain" if mime_type == "text/markdown" else mime_type,
                    headers={"Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(document['original_filename'], safe='')}",
                             "X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"})


@router.delete("/{document_id}")
def delete(document_id: str, user=Depends(require_current_user), knowledge=Depends(service)):
    return knowledge.delete(user.account_id, document_id)
