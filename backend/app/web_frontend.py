"""Serve an explicitly configured build without exposing application source or data."""
from pathlib import Path
from fastapi import FastAPI
from starlette.exceptions import HTTPException
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, root: str):
    directory = Path(root).resolve(strict=True)
    if not (directory / "index.html").is_file():
        raise ValueError("SERENITA_FRONTEND_ROOT must contain a built index.html")

    class FrontendFiles(StaticFiles):
        async def get_response(self, path, scope):
            if path == "api" or path.startswith("api/"):
                raise HTTPException(404)
            if path in {"admin", "server"} or path.startswith(("admin/", "server/")):
                raise HTTPException(404)
            try:
                return await super().get_response(path, scope)
            except HTTPException as error:
                if error.status_code != 404 or "." in Path(path).name:
                    raise
                return FileResponse(directory / "index.html", headers={"Cache-Control": "no-cache"})

    app.mount("/", FrontendFiles(directory=directory, html=True), name="frontend")
